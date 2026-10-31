from dataclasses import replace
from pathlib import Path
from threading import Event, get_ident

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QPushButton

from clipflow.application.errors import JobRuleError
from clipflow.application.scheduler import Scheduler
from clipflow.application.submission import SubmissionService
from clipflow.domain.events import JobEvent, ProgressChanged, StageChanged, TitleChanged
from clipflow.domain.models import (
    ContentKind,
    DownloadOptions,
    DownloadRequest,
    Job,
    JobState,
    Service,
)
from clipflow.domain.urls import parse_url
from clipflow.infrastructure.executor import ThreadExecutor
from clipflow.infrastructure.repository import SqliteJobRepository
from clipflow.infrastructure.settings import AppSettings
from clipflow.providers.base import DownloadResult, MediaItem
from clipflow.ui.presenter import WorkbenchPresenter
from clipflow.ui.queue_model import JobListModel
from clipflow.ui.window import MainWindow
from tests.instagram_fixtures import Auth
from tests.integration.test_media_pipeline import (
    media_server,
    tools,
)  # real local HTTP/FFmpeg fixtures


class HeldProvider:
    def __init__(self):
        self.started = Event()
        self.released = Event()
        self.torn_down = Event()
        self.thread = None

    def execute(self, request, context):
        self.thread = get_ident()
        self.started.set()
        try:
            context.emit(TitleChanged('Настоящее название'))
            context.emit(StageChanged(JobState.DOWNLOADING))
            context.emit(ProgressChanged(25, 100))
            while not self.released.is_set():
                if context.cancel.wait(0.005):
                    context.cancel.raise_if_cancelled()
            return DownloadResult(())
        finally:
            self.torn_down.set()


@pytest.fixture
def make_window(qtbot, tmp_path):
    windows = []

    def make(provider=None, repository=None, settings=None):
        provider = provider or HeldProvider()
        repository = repository or SqliteJobRepository(tmp_path / f'queue-{len(windows)}.sqlite3')
        presets = {s: DownloadOptions(tmp_path / 'downloads') for s in Service}
        settings = settings or AppSettings(presets=presets)
        executor = ThreadExecutor({(Service.YOUTUBE, ContentKind.VIDEO): provider}, Auth())
        scheduler = Scheduler(repository, executor)
        presenter = WorkbenchPresenter(
            SubmissionService(repository), scheduler, settings, repository
        )
        # This fixture owns teardown: pytest-qt deletes registered widgets even
        # when closeEvent correctly waits for an asynchronous worker.
        window = MainWindow(presenter)
        window.show()
        windows.append(window)
        return window, provider

    yield make
    for window in windows:
        window.presenter.shutdown()
        qtbot.waitUntil(lambda w=window: w.presenter.is_closed, timeout=5000)
        window.close()
        window.deleteLater()


def add(window, qtbot, url='https://youtu.be/ABC'):
    window.url_input.setText(url)
    qtbot.mouseClick(window.add_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.presenter.model.rowCount() > 0)
    return window.presenter.model.jobs[0].id


def test_real_url_command_creates_model_row(make_window, qtbot):
    window, provider = make_window()
    identity = add(window, qtbot)
    assert window.url_input.text() == ''
    assert window.presenter.repository.get(identity).state == JobState.QUEUED
    assert window.queue_view.model().rowCount() == 1 and not provider.started.is_set()
    assert (
        window.presenter.model.data(
            window.presenter.model.index(0), window.presenter.model.SourceRole
        )
        == 'youtube'
    )


def test_worker_events_update_correct_attempt(make_window, qtbot):
    window, provider = make_window()
    identity = add(window, qtbot)
    owner = get_ident()
    changes = []
    window.presenter.model.dataChanged.connect(lambda *args: changes.append(get_ident()))
    window.presenter.toggle_job(identity)
    qtbot.waitUntil(lambda: window.presenter.repository.get(identity).state == JobState.DOWNLOADING)
    assert provider.thread != owner and changes and set(changes) == {owner}
    model = window.presenter.model
    index = model.index(0)
    assert model.data(index, model.TitleRole) == 'Настоящее название'
    window.presenter.scheduler.handle(JobEvent(identity, 'stale-attempt', TitleChanged('WRONG')))
    window.presenter.scheduler.handle(JobEvent(identity, 'stale-attempt', ProgressChanged(99, 100)))
    assert model.data(index, model.TitleRole) == 'Настоящее название'
    assert model.data(index, model.ProgressRole).downloaded_bytes == 25


def test_local_media_download_reaches_real_completed_file(
    make_window, qtbot, media_server, tools, tmp_path
):
    from clipflow.providers.media import MediaPipeline
    from clipflow.providers.youtube import YouTubeProvider

    class LocalProvider(YouTubeProvider):
        def _extract(self, request, context):
            return {
                'id': 'ABC',
                'title': 'Local video',
                'url': media_server[0] + '/sample.mp4',
                'ext': 'mp4',
            }

    window, _ = make_window(LocalProvider(MediaPipeline()))
    identity = add(window, qtbot)
    titles = []
    window.presenter.scheduler.subscribe(
        lambda e: titles.append(e.payload.title) if isinstance(e.payload, TitleChanged) else None
    )
    qtbot.mouseClick(window.start_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(
        lambda: window.presenter.repository.get(identity).state == JobState.COMPLETED, timeout=15000
    )
    saved = window.presenter.repository.get(identity).result_files
    assert len(saved) == 1 and saved[0].is_file() and saved[0].stat().st_size > 0
    assert titles == ['Local video']
    from tests.integration.test_media_pipeline import probe

    assert 'mp4' in probe(saved[0], tools)['format']['format_name']
    path = window.presenter.repository.path
    restored = SqliteJobRepository(path)
    try:
        assert restored.history()[0].result_files == saved
    finally:
        restored.close()


def test_window_minimum_880x680(make_window, qtbot):
    window, _ = make_window()
    window.resize(880, 680)
    assert window.minimumWidth() == 880 and window.minimumHeight() == 680
    # QScrollArea applies the viewport's resize in the next event-loop turn.
    qtbot.waitUntil(lambda: window.url_input.width() >= 180)
    assert window.url_input.width() > 150 and window.add_button.width() >= 150
    qtbot.waitUntil(lambda: window.composer_host.horizontalScrollBar().maximum() == 0)


def test_large_queue_uses_model_not_child_widgets(make_window, tmp_path):
    from tests.helpers import MemoryJobRepository

    repo = MemoryJobRepository()
    for n in range(1000):
        repo.add(
            Job(
                str(n),
                DownloadRequest(parse_url(f'https://youtu.be/id{n}'), DownloadOptions(tmp_path)),
            )
        )
    window, _ = make_window(repository=repo)
    assert window.presenter.model.rowCount() == 1000
    assert len(window.findChildren(QPushButton)) < 30
    assert window.queue_view.indexWidget(window.queue_view.model().index(0, 0)) is None


def test_blocking_provider_does_not_block_gui_timer(make_window, qtbot):
    window, provider = make_window()
    identity = add(window, qtbot)
    ticks = []
    timer = QTimer()
    timer.setInterval(10)
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start()
    window.presenter.toggle_job(identity)
    qtbot.waitUntil(lambda: provider.started.is_set() and len(ticks) >= 5, timeout=1500)
    assert not provider.torn_down.is_set()
    window.presenter.toggle_job(identity)
    qtbot.waitUntil(lambda: provider.torn_down.is_set())
    assert window.presenter.repository.get(identity).state == JobState.PAUSED
    timer.stop()


def test_close_waits_for_worker_teardown_and_persists_pause(make_window, qtbot):
    window, provider = make_window()
    identity = add(window, qtbot)
    window.presenter.toggle_job(identity)
    qtbot.waitUntil(lambda: provider.started.is_set())
    path = window.presenter.repository.path
    window.close()
    qtbot.waitUntil(lambda: window.presenter.is_closed)
    assert provider.torn_down.is_set()
    restored = SqliteJobRepository(path)
    try:
        assert restored.get(identity).state == JobState.PAUSED
    finally:
        restored.close()


def test_invalid_link_kept_and_duplicate_does_not_create_row(make_window, qtbot):
    window, _ = make_window()
    window.url_input.setText('invalid')
    qtbot.mouseClick(window.add_button, Qt.MouseButton.LeftButton)
    assert window.url_input.text() == 'invalid' and window.presenter.model.rowCount() == 0
    add(window, qtbot)
    window.url_input.setText('https://youtu.be/ABC')
    qtbot.mouseClick(window.add_button, Qt.MouseButton.LeftButton)
    assert window.presenter.model.rowCount() == 1


def test_selected_queued_job_starts_without_parallel_worker(make_window, qtbot):
    window, provider = make_window()
    add(window, qtbot)
    window.url_input.setText('https://youtu.be/DEF')
    qtbot.mouseClick(window.add_button, Qt.MouseButton.LeftButton)
    jobs = window.presenter.repository.list()
    window.presenter.toggle_job(jobs[1].id)
    qtbot.waitUntil(lambda: provider.started.is_set())
    assert window.presenter.repository.get(jobs[0].id).state == JobState.QUEUED
    assert window.presenter.repository.get(jobs[1].id).state in {
        JobState.PROBING,
        JobState.DOWNLOADING,
    }


def test_bootstrap_recovers_without_network_and_dark_first(qtbot, tmp_path):
    from clipflow.ui.bootstrap import create_application

    repo = SqliteJobRepository(tmp_path / 'queue.sqlite3')
    repo.add(
        Job(
            'old',
            DownloadRequest(parse_url('https://youtu.be/ABC'), DownloadOptions(tmp_path)),
            JobState.DOWNLOADING,
        )
    )
    repo.close()
    app, window = create_application(['clipflow-test'], data_dir=tmp_path)
    qtbot.addWidget(window)
    try:
        assert window.presenter.repository.get('old').state == JobState.PAUSED
        assert window.presenter.executor.is_idle
        assert app.palette().window().color().lightness() < 70
    finally:
        window.presenter.shutdown()
        qtbot.waitUntil(lambda: window.presenter.is_closed)


def test_selection_can_refresh_after_restart(make_window, qtbot, tmp_path):
    from PySide6.QtWidgets import QDialogButtonBox

    from clipflow.domain.events import SelectionRequired

    class SelectProvider:
        def execute(self, request, context):
            if request.selection is None:
                context.emit(
                    SelectionRequired(('first', 'second'), ('Первое видео', 'Второе видео'))
                )
            return DownloadResult(())

    repo = SqliteJobRepository(tmp_path / 'selection.sqlite3')
    request = DownloadRequest(parse_url('https://youtu.be/ABC'), DownloadOptions(tmp_path))
    repo.add(Job('choose', request, JobState.PAUSED, pause_reason='selection_required'))
    window, _ = make_window(SelectProvider(), repository=repo)
    window.presenter.toggle_job('choose')
    qtbot.waitUntil(lambda: bool(window._dialogs), timeout=2000)
    dialog = window._dialogs[0]
    assert dialog.findChild(QDialogButtonBox) is not None
    from PySide6.QtWidgets import QListWidget

    assert dialog.findChild(QListWidget).item(0).text() == 'Первое видео'
    dialog.reject()


def test_progress_burst_throttled_but_critical_title_and_failure_immediate(make_window, qtbot):
    from clipflow.providers.base import MediaFailure

    class BurstProvider:
        def execute(self, request, context):
            for n in range(3000):
                context.emit(ProgressChanged(n, 3000))
            context.emit(TitleChanged('Final metadata'))
            raise MediaFailure('download_failed')

    window, _ = make_window(BurstProvider())
    identity = add(window, qtbot)
    events = []
    window.presenter.scheduler.subscribe(events.append)
    window.presenter.toggle_job(identity)
    qtbot.waitUntil(lambda: window.presenter.repository.get(identity).state == JobState.FAILED)
    assert len([event for event in events if isinstance(event.payload, ProgressChanged)]) <= 2
    assert (
        window.presenter.model.data(window.presenter.model.index(0), JobListModel.TitleRole)
        == 'Final metadata'
    )


def test_shutdown_keeps_slot_until_actual_teardown(make_window, qtbot):
    from time import sleep

    class SlowStop(HeldProvider):
        def execute(self, request, context):
            self.started.set()
            try:
                while not context.cancel.wait(0.005):
                    pass
                sleep(0.08)
                context.cancel.raise_if_cancelled()
            finally:
                self.torn_down.set()

    window, provider = make_window(SlowStop())
    identity = add(window, qtbot)
    window.presenter.toggle_job(identity)
    qtbot.waitUntil(provider.started.is_set)
    window.close()
    assert not window.presenter.is_closed
    qtbot.waitUntil(lambda: window.presenter.is_closed)
    assert provider.torn_down.is_set()


def test_failed_folder_save_cannot_queue_with_old_destination(make_window, qtbot, tmp_path):
    from clipflow.infrastructure.settings import SettingsError

    class FailingStore:
        def save(self, settings):
            raise SettingsError('storage_read_only')

    window, _ = make_window()
    window.presenter.settings_store = FailingStore()
    window.url_input.setText('https://youtu.be/ABC')
    window.folder_input.setText(str(tmp_path / 'new-folder'))
    qtbot.mouseClick(window.add_button, Qt.MouseButton.LeftButton)
    assert (
        window.presenter.model.rowCount() == 0 and window.url_input.text() == 'https://youtu.be/ABC'
    )
    assert window.error_label.isVisible()


def test_startup_storage_failure_is_actionable_without_traceback(qtbot, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from clipflow.infrastructure.settings import SettingsError, SettingsStore
    from clipflow.ui.bootstrap import main

    messages = []

    def fail(self):
        raise SettingsError('storage_read_only')

    monkeypatch.setattr(SettingsStore, 'load', fail)
    monkeypatch.setattr(QMessageBox, 'critical', lambda *args: messages.append(args[2]))
    assert main(['clipflow-test']) == 1
    assert messages and 'записи' in messages[0]


@pytest.mark.parametrize('activation_key', [Qt.Key.Key_Return, Qt.Key.Key_Enter])
def test_real_row_pause_resume_cancel_controls(make_window, qtbot, activation_key):
    from PySide6.QtCore import QPoint

    window, provider = make_window()
    identity = add(window, qtbot)
    index = window.queue_view.model().index(0, 0)
    rect = window.queue_view.visualRect(index)
    primary = QPoint(rect.right() - 65, rect.top() + 41)
    qtbot.mouseClick(window.queue_view.viewport(), Qt.MouseButton.LeftButton, pos=primary)
    qtbot.waitUntil(lambda: window.presenter.repository.get(identity).state == JobState.DOWNLOADING)
    qtbot.mouseClick(window.queue_view.viewport(), Qt.MouseButton.LeftButton, pos=primary)
    qtbot.waitUntil(lambda: window.presenter.executor.is_idle)
    assert window.presenter.repository.get(identity).state == JobState.PAUSED
    window.queue_view.setCurrentIndex(index)
    modifier = (
        Qt.KeyboardModifier.KeypadModifier
        if activation_key == Qt.Key.Key_Enter
        else Qt.KeyboardModifier.NoModifier
    )
    qtbot.keyClick(window.queue_view, activation_key, modifier)
    qtbot.waitUntil(lambda: window.presenter.repository.get(identity).state == JobState.DOWNLOADING)
    qtbot.mouseClick(
        window.queue_view.viewport(),
        Qt.MouseButton.LeftButton,
        pos=QPoint(rect.right() - 27, rect.top() + 41),
    )
    qtbot.waitUntil(lambda: window.presenter.executor.is_idle)
    assert window.presenter.repository.get(identity).state == JobState.CANCELLED


def test_held_return_does_not_pause_the_just_started_job(make_window, qtbot):
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QApplication

    window, provider = make_window()
    identity = add(window, qtbot)
    window.queue_view.setCurrentIndex(window.queue_view.model().index(0, 0))
    activations = []
    window.queue_view.activated.connect(lambda index: activations.append(index.row()))
    qtbot.keyClick(window.queue_view, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: window.presenter.repository.get(identity).state == JobState.DOWNLOADING)
    QApplication.sendEvent(
        window.queue_view,
        QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier, '', True, 2
        ),
    )
    assert (
        activations == [0]
        and window.presenter.repository.get(identity).state == JobState.DOWNLOADING
    )


def test_navigation_and_auto_start_keep_input_and_snapshot(make_window, qtbot):
    window, provider = make_window()
    identity = add(window, qtbot)
    window.url_input.setText('draft')
    qtbot.mouseClick(window.nav_buttons[1], Qt.MouseButton.LeftButton)
    assert window.proxy.rowCount() == 0 and not window.composer.isVisible()
    qtbot.mouseClick(window.nav_buttons[0], Qt.MouseButton.LeftButton)
    assert window.url_input.text() == 'draft' and window.proxy.rowCount() == 1
    window.composer.parameters_button.setChecked(True)
    qtbot.mouseClick(window.auto_start, Qt.MouseButton.LeftButton)
    assert window.presenter.settings.auto_start
    window.url_input.setText('https://youtu.be/DEF')
    qtbot.mouseClick(window.add_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(provider.started.is_set)
    assert len(window.presenter.repository.list()) == 2
    assert (
        window.presenter.repository.get(identity).request.options.folder
        == window.presenter.settings.presets[Service.YOUTUBE].folder
    )


def test_repository_write_failure_stops_workers_and_closes_safely(make_window, qtbot, monkeypatch):
    from clipflow.infrastructure.repository import RepositoryError

    window, provider = make_window()
    identity = add(window, qtbot)
    update = window.presenter.repository.update

    def fail(job):
        if job.state == JobState.DOWNLOADING:
            raise RepositoryError('storage_full')
        return update(job)

    monkeypatch.setattr(window.presenter.repository, 'update', fail)
    window.presenter.toggle_job(identity)
    qtbot.waitUntil(lambda: window.presenter.is_closed)
    assert provider.torn_down.is_set() and window.error_label.isVisible()


def test_completed_row_opens_result_directory_without_deleting(
    make_window, qtbot, tmp_path, monkeypatch
):
    from PySide6.QtGui import QDesktopServices

    repo = SqliteJobRepository(tmp_path / 'history.sqlite3')
    media = tmp_path / 'saved.mp4'
    media.write_bytes(b'synthetic-file-for-folder-action')
    request = DownloadRequest(parse_url('https://youtu.be/ABC'), DownloadOptions(tmp_path))
    repo.add(Job('done', request, JobState.COMPLETED, result_files=(media,)))
    window, _ = make_window(repository=repo)
    opened = []
    monkeypatch.setattr(
        QDesktopServices, 'openUrl', lambda url: opened.append(url.toLocalFile()) or True
    )
    window.presenter.toggle_job('done')
    assert [Path(value) for value in opened] == [tmp_path] and media.exists()


def test_drain_reaps_active_worker_after_event_loop_exit(make_window, qtbot):
    window, provider = make_window()
    identity = add(window, qtbot)
    window.presenter.toggle_job(identity)
    qtbot.waitUntil(provider.started.is_set)
    window.presenter.shutdown()
    window.presenter.executor.drain()
    assert provider.torn_down.is_set() and window.presenter.is_closed


def test_instagram_rate_limit_releases_real_qt_executor_for_youtube(make_window, qtbot, tmp_path):
    from clipflow.application.instagram_rate_policy import InstagramDeferred, InstagramRatePolicy
    from clipflow.infrastructure.rate_limit_store import RateLimitStore

    policy = InstagramRatePolicy(
        RateLimitStore(tmp_path / 'instagram-rate.sqlite3'), random=lambda: 0
    )
    captured = []

    class LimitedProvider:
        def execute(self, request, context):
            captured.append(context.instagram_rate)
            decision = context.instagram_rate.record_429('900')
            context.emit(decision)
            raise InstagramDeferred(decision)

    window, youtube = make_window()
    executor = window.presenter.executor
    executor.registry[(Service.INSTAGRAM, ContentKind.POST)] = LimitedProvider()
    executor.instagram_rate = policy
    first = add(window, qtbot, 'https://instagram.com/p/ABC/')
    window.url_input.setText('https://youtu.be/DEF')
    qtbot.mouseClick(window.add_button, Qt.MouseButton.LeftButton)
    window.presenter.start_queue()
    qtbot.waitUntil(youtube.started.is_set)
    job = window.presenter.repository.get(first)
    assert (
        captured == [policy] and job.state == JobState.PAUSED and job.pause_reason == 'rate_limit'
    )
    assert job.automatic_retry and job.next_allowed_at is not None


@pytest.mark.parametrize(
    ('error', 'code'),
    [
        (JobRuleError('cooldown_active', 'Cooldown has not expired'), 'cooldown_active'),
        (JobRuleError('job_not_startable', 'Job cannot be started'), 'job_not_startable'),
        # The code comes from the error type, never from its English message.
        (ValueError('Cooldown has not expired'), 'action_failed'),
        (ValueError('Source changed; add it as a new job'), 'action_failed'),
    ],
)
def test_command_errors_use_codes_not_message_text(make_window, qtbot, monkeypatch, error, code):
    window, _ = make_window()

    def fail(identity=None):
        raise error

    monkeypatch.setattr(window.presenter.scheduler, 'start', fail)
    with qtbot.waitSignal(window.presenter.error_raised) as raised:
        window.presenter.start_queue()
    assert raised.args == [code]


def test_window_exposes_the_widgets_of_its_parts(make_window):
    window, _ = make_window()
    panel, sidebar = window.queue_panel, window.sidebar
    assert window.start_button is panel.start_button
    assert window.cancel_queue_button is panel.cancel_queue_button
    assert window.clear_all_button is panel.clear_all_button
    assert window.queue_view is panel.queue_view
    assert window.proxy is panel.proxy
    assert window.status_buttons is panel.status_buttons
    assert window.nav_buttons is sidebar.nav_buttons
    assert window.accounts_button is sidebar.accounts_button
    assert window.settings_button is sidebar.settings_button
