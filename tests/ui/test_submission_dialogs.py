from dataclasses import replace
from threading import Event

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialogButtonBox, QListWidget

from clipflow.domain.events import SelectionRequired
from clipflow.domain.models import ContentKind, DownloadOptions, JobState, Service
from clipflow.providers.base import DownloadResult, ProbeResult
from clipflow.ui.batch_dialog import BatchDialog
from clipflow.ui.composer import Composer
from tests.support.workbench import batch


def test_music_locks_mp3_and_restores_video_preset(make_window, qtbot, tmp_path, monkeypatch):
    window, _ = make_window()
    composer = window.composer
    composer.format_box.setCurrentIndex(composer.format_box.findData('mkv'))
    window.url_input.setText('https://music.youtube.com/watch?v=track')
    assert composer.format_box.currentData() == 'mp3' and not composer.format_box.isEnabled()
    assert not composer.quality_box.isEnabled() and composer.options().format == 'mp3'
    composer.folder_input.setText(str(tmp_path / 'other'))
    composer.folder_input.editingFinished.emit()
    assert window.presenter.settings.presets[Service.YOUTUBE].format == 'mkv'
    composer.apply_probe('obsolete', (1080,), '')
    assert composer.format_box.currentData() == 'mp3'
    window.url_input.setText('https://youtube.com/watch?v=video')
    assert composer.format_box.currentData() == 'mkv' and composer.format_box.isEnabled()
    assert composer.options().folder == tmp_path / 'other'
    window.url_input.setText('https://music.youtube.com/watch?v=track')
    window.url_input.clear()
    assert composer.format_box.currentData() == 'mkv' and composer.format_box.isEnabled()
    from types import SimpleNamespace

    from PySide6.QtWidgets import QApplication

    # Native clipboard mechanics have their own platform tests. Isolate this
    # format-switch test so it cannot contaminate those tests' MIME ownership.
    with monkeypatch.context() as patch:
        patch.setattr(
            QApplication,
            'clipboard',
            staticmethod(
                lambda: SimpleNamespace(text=lambda: 'https://music.youtube.com/watch?v=track')
            ),
        )
        qtbot.mouseClick(composer.paste_button, Qt.MouseButton.LeftButton)
    assert composer.format_box.currentData() == 'mp3' and not composer.format_box.isEnabled()
    composer.set_service(Service.INSTAGRAM)
    composer.set_service(Service.YOUTUBE)
    assert composer.format_box.currentData() == 'mp3'
    window.url_input.clear()
    assert composer.format_box.currentData() == 'mkv'


@pytest.mark.parametrize('action', ['submit', 'batch'])
def test_music_commit_does_not_change_normal_youtube_preset(make_window, qtbot, action):
    window, _ = make_window()
    composer = window.composer
    composer.format_box.setCurrentIndex(composer.format_box.findData('mkv'))
    window.url_input.setText('https://music.youtube.com/watch?v=track')
    if action == 'submit':
        qtbot.mouseClick(composer.add_button, Qt.MouseButton.LeftButton)
        assert window.presenter.repository.list()[0].request.options.format == 'mp3'
        assert not window.url_input.text()
    else:
        dialog = batch(window, qtbot)
        dialog.text_input.setPlainText(
            'https://music.youtube.com/watch?v=track\nhttps://youtube.com/watch?v=video'
        )
        assert [r.options.format for r in dialog.preview().requests] == ['mp3', 'mkv']
        dialog.reject()
    assert window.presenter.settings.presets[Service.YOUTUBE].format == 'mkv'
    window.url_input.setText('https://youtube.com/watch?v=other')
    assert composer.format_box.currentData() == 'mkv'


def test_matching_music_probe_never_displays_video_height(make_window, qtbot):
    window, _ = make_window()
    composer = window.composer
    composer.quality_box.addItem('720p', 720)
    composer.quality_box.setCurrentIndex(composer.quality_box.findData(720))
    assert window.presenter.settings.presets[Service.YOUTUBE].max_height == 720
    window.url_input.setText('https://music.youtube.com/watch?v=track')
    composer.apply_probe(composer._probe_id, (), '')
    assert composer.quality_box.currentData() is None and composer.quality_box.count() == 1
    window.url_input.clear()
    assert composer.quality_box.currentData() == 720


def test_batch_button_always_visible(make_window, qtbot):
    window, _ = make_window()
    for button in window.nav_buttons:
        qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
        assert window.batch_button.isVisible() and window.batch_button.isEnabled()
    dialog = batch(window, qtbot)
    assert dialog.isVisible()


def test_mixed_batch_adds_three_services_and_profile(make_window, qtbot, tmp_path):
    window, _ = make_window()
    presets = {
        service: DownloadOptions(tmp_path / service.value, format=fmt)
        for service, fmt in [
            (Service.YOUTUBE, 'mkv'),
            (Service.INSTAGRAM, 'webm'),
            (Service.GETCOURSE, 'mp4'),
        ]
    }
    window.presenter.settings = replace(
        window.presenter.settings, presets=presets, profile_limit=50
    )
    window.presenter.settings_changed.emit()
    window.url_input.setText('my unfinished draft')
    dialog = batch(window, qtbot)
    dialog.text_input.setPlainText(
        '\n'.join(
            [
                'https://youtu.be/ABC',
                'https://instagram.com/p/POST/',
                'https://school.getcourse.ru/pl/teach/control/lesson/view?id=123',
                'https://instagram.com/alice/',
            ]
        )
    )
    assert len(dialog.preview().requests) == 4 and window.presenter.repository.list() == ()
    qtbot.mouseClick(dialog.accept_button, Qt.MouseButton.LeftButton)
    jobs = window.presenter.repository.list()
    assert len(jobs) == 4 and {job.request.link.service for job in jobs} == set(Service)
    for job in jobs:
        assert job.request.options == presets[job.request.link.service]
    assert jobs[-1].request.profile_limit == 50 and jobs[-1].request.options.post_folder
    assert window.url_input.text() == 'my unfinished draft'


def test_bad_line_does_not_block_valid_lines(make_window, qtbot):
    window, _ = make_window()
    dialog = batch(window, qtbot)
    dialog.text_input.setPlainText(
        'https://youtu.be/ABC\nnot a link\nhttps://instagram.com/p/POST/\nhttps://youtu.be/ABC?x=1'
    )
    preview = dialog.preview()
    assert (
        len(preview.requests) == 2
        and preview.invalid[0].line == 2
        and preview.duplicate_lines == (4,)
    )
    assert dialog.accept_button.isEnabled()
    qtbot.mouseClick(dialog.accept_button, Qt.MouseButton.LeftButton)
    assert len(window.presenter.repository.list()) == 2


def test_single_profile_requires_explicit_mode(make_window, qtbot):
    window, _ = make_window()
    window.composer.set_service(Service.INSTAGRAM)
    window.url_input.setText('https://instagram.com/alice/')
    assert '«Профиль»' in window.composer.hint.text()
    qtbot.mouseClick(window.add_button, Qt.MouseButton.LeftButton)
    assert window.presenter.repository.list() == () and window.url_input.text()
    qtbot.mouseClick(window.composer.mode_buttons['profile'], Qt.MouseButton.LeftButton)
    qtbot.mouseClick(window.add_button, Qt.MouseButton.LeftButton)
    assert window.presenter.repository.list()[0].request.link.kind == ContentKind.PROFILE


@pytest.mark.parametrize('limit', [10, 50, None])
def test_profile_10_50_all(make_window, qtbot, limit):
    window, _ = make_window()
    composer = window.composer
    composer.set_service(Service.INSTAGRAM)
    qtbot.mouseClick(composer.mode_buttons['profile'], Qt.MouseButton.LeftButton)
    composer.limit_box.setCurrentIndex(composer.limit_box.findData(limit))
    window.url_input.setText('https://instagram.com/alice/')
    qtbot.keyClick(window.url_input, Qt.Key.Key_Return)
    job = window.presenter.repository.list()[0]
    assert job.request.profile_limit == limit and job.request.options.post_folder
    assert not composer.post_folder.isEnabled()


def test_input_changed_during_probe_not_cleared(make_window, qtbot):
    class Prober:
        def __init__(self):
            self.started = Event()
            self.release = Event()

        def probe(self, request, context):
            self.started.set()
            while not self.release.wait(0.005):
                if context.cancel.wait(0.001):
                    context.cancel.raise_if_cancelled()
            return ProbeResult((), (1080, 720))

        def execute(self, *args):
            return DownloadResult(())

    prober = Prober()
    window, _ = make_window(prober)
    window.url_input.setText('https://youtu.be/OLD')
    qtbot.waitUntil(prober.started.is_set)
    window.url_input.setText('new unfinished text')
    prober.release.set()
    qtbot.waitUntil(lambda: window.presenter.executor.is_idle)
    assert window.url_input.text() == 'new unfinished text' and not window.composer.quality_pending
    assert window.composer.quality_box.count() == 1


def test_quality_pending_does_not_drop_batch(make_window, qtbot):
    class Prober:
        def __init__(self):
            self.started = Event()

        def probe(self, request, context):
            self.started.set()
            while not context.cancel.wait(0.01):
                pass
            context.cancel.raise_if_cancelled()

        def execute(self, *args):
            return DownloadResult(())

    prober = Prober()
    window, _ = make_window(prober)
    window.url_input.setText('https://youtu.be/OLD')
    qtbot.waitUntil(prober.started.is_set)
    assert window.composer.quality_pending
    dialog = batch(window, qtbot)
    dialog.text_input.setPlainText('https://youtu.be/NEW\nhttps://instagram.com/p/POST/')
    qtbot.mouseClick(dialog.accept_button, Qt.MouseButton.LeftButton)
    assert len(window.presenter.repository.list()) == 2
    assert window.url_input.text() == 'https://youtu.be/OLD'


def test_cancel_dialog_adds_nothing(make_window, qtbot):
    window, _ = make_window()
    dialog = batch(window, qtbot)
    dialog.text_input.setPlainText('https://youtu.be/ABC')
    qtbot.mouseClick(dialog.cancel_button, Qt.MouseButton.LeftButton)
    assert window.presenter.repository.list() == ()


def test_getcourse_media_selection(make_window, qtbot):
    class Lesson:
        def probe(self, request, context):
            return ProbeResult((), ())

        def execute(self, request, context):
            if request.selection is None:
                context.emit(
                    SelectionRequired(('one', 'two'), ('Первый материал', 'Второй материал'))
                )
            return DownloadResult(())

    window, _ = make_window()
    window.presenter.executor.registry[(Service.GETCOURSE, ContentKind.LESSON)] = Lesson()
    window.composer.set_service(Service.GETCOURSE)
    window.url_input.setText('https://school.getcourse.ru/pl/teach/control/lesson/view?id=123')
    qtbot.mouseClick(window.add_button, Qt.MouseButton.LeftButton)
    identity = window.presenter.repository.list()[0].id
    window.presenter.toggle_job(identity)
    qtbot.waitUntil(lambda: any(dialog.findChild(QListWidget) for dialog in window._dialogs))
    dialog = next(dialog for dialog in window._dialogs if dialog.findChild(QListWidget))
    choices = dialog.findChild(QListWidget)
    assert choices.item(0).text() == 'Первый материал'
    choices.item(1).setCheckState(Qt.CheckState.Unchecked)
    qtbot.mouseClick(
        dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok),
        Qt.MouseButton.LeftButton,
    )
    qtbot.waitUntil(lambda: window.presenter.repository.get(identity).request.selection == ('one',))


def test_service_drafts_and_options_are_independent(make_window, qtbot):
    window, _ = make_window()
    composer = window.composer
    composer.set_service(Service.YOUTUBE)
    window.url_input.setText('YouTube draft')
    composer.format_box.setCurrentIndex(composer.format_box.findData('mkv'))
    composer.set_service(Service.INSTAGRAM)
    window.url_input.setText('Instagram draft')
    composer.format_box.setCurrentIndex(composer.format_box.findData('webm'))
    composer.set_service(Service.YOUTUBE)
    assert window.url_input.text() == 'YouTube draft' and composer.format_box.currentData() == 'mkv'
    composer.set_service(Service.INSTAGRAM)
    assert (
        window.url_input.text() == 'Instagram draft' and composer.format_box.currentData() == 'webm'
    )


def test_quality_probe_is_async_cached_and_does_not_change_best_default(make_window, qtbot):
    class Prober:
        def __init__(self):
            self.calls = 0

        def probe(self, request, context):
            self.calls += 1
            return ProbeResult((), (720, 2160, 1080, 720))

        def execute(self, *args):
            return DownloadResult(())

    prober = Prober()
    window, _ = make_window(prober)
    composer = window.composer
    window.url_input.setText('https://youtu.be/ABC')
    qtbot.waitUntil(lambda: not composer.quality_pending)
    assert [composer.quality_box.itemData(n) for n in range(composer.quality_box.count())] == [
        None,
        2160,
        1080,
        720,
    ]
    assert composer.quality_box.currentData() is None and prober.calls == 1
    window.url_input.clear()
    window.url_input.setText('https://youtu.be/ABC')
    qtbot.waitUntil(lambda: not composer.quality_pending)
    assert prober.calls == 1


def test_link_without_qualities_is_cached_too(make_window, qtbot):
    class Prober:
        calls = 0

        def probe(self, request, context):
            Prober.calls += 1
            return ProbeResult((), ())

        def execute(self, *args):
            return DownloadResult(())

    window, _ = make_window(Prober())
    composer = window.composer
    for _ in range(2):
        window.url_input.clear()
        window.url_input.setText('https://youtu.be/ABC')
        qtbot.waitUntil(lambda: not composer.quality_pending)
    assert Prober.calls == 1


def test_autostart_waits_for_probe_teardown_instead_of_failing_job(make_window, qtbot):
    from tests.support.workbench import HeldProvider

    class Prober(HeldProvider):
        def __init__(self):
            super().__init__()
            self.probe_started = Event()
            self.probe_closed = Event()

        def probe(self, request, context):
            self.probe_started.set()
            try:
                while not context.cancel.wait(0.005):
                    pass
                context.cancel.raise_if_cancelled()
            finally:
                self.probe_closed.set()

        def execute(self, request, context):
            assert self.probe_closed.is_set()
            return super().execute(request, context)

    prober = Prober()
    window, _ = make_window(prober)
    window.composer.parameters_button.setChecked(True)
    qtbot.mouseClick(window.auto_start, Qt.MouseButton.LeftButton)
    window.url_input.setText('https://youtu.be/ABC')
    qtbot.waitUntil(prober.probe_started.is_set)
    qtbot.mouseClick(window.add_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(prober.started.is_set)
    job = window.presenter.repository.list()[0]
    assert job.state in {JobState.PROBING, JobState.DOWNLOADING} and job.error is None


def test_batch_snapshot_does_not_follow_later_preset_changes(make_window, qtbot, tmp_path):
    window, _ = make_window()
    dialog = batch(window, qtbot)
    dialog.text_input.setPlainText('https://youtu.be/ABC')
    original = dialog.preview().requests[0].options
    window.presenter.update_preset(
        Service.YOUTUBE, replace(original, folder=tmp_path / 'elsewhere', format='mp3')
    )
    qtbot.mouseClick(dialog.accept_button, Qt.MouseButton.LeftButton)
    assert window.presenter.repository.list()[0].request.options == original


def test_profile_forces_folder_without_overwriting_single_post_preference(make_window, qtbot):
    window, _ = make_window()
    composer = window.composer
    composer.set_service(Service.INSTAGRAM)
    composer.post_folder.setChecked(False)
    qtbot.mouseClick(composer.mode_buttons['profile'], Qt.MouseButton.LeftButton)
    assert composer.post_folder.isChecked() and not composer.post_folder.isEnabled()
    window.url_input.setText('https://instagram.com/alice/')
    qtbot.mouseClick(window.add_button, Qt.MouseButton.LeftButton)
    assert window.presenter.repository.list()[0].request.options.post_folder
    qtbot.mouseClick(composer.mode_buttons['single'], Qt.MouseButton.LeftButton)
    assert composer.post_folder.isEnabled() and not composer.post_folder.isChecked()


def test_batch_storage_failure_keeps_dialog_and_input(make_window, qtbot, monkeypatch):
    from clipflow.infrastructure.repository import RepositoryError

    window, _ = make_window()
    dialog = batch(window, qtbot)
    text = 'https://youtu.be/ABC'
    dialog.text_input.setPlainText(text)

    def fail(job):
        raise RepositoryError('storage_read_only')

    monkeypatch.setattr(window.presenter.repository, 'add', fail)
    qtbot.mouseClick(dialog.accept_button, Qt.MouseButton.LeftButton)
    assert (
        dialog.isVisible()
        and dialog.text_input.toPlainText() == text
        and window.presenter.repository.list() == ()
    )


def test_batch_shows_already_queued_without_creating_copy(make_window, qtbot):
    window, _ = make_window()
    window.url_input.setText('https://youtu.be/ABC')
    qtbot.mouseClick(window.add_button, Qt.MouseButton.LeftButton)
    dialog = batch(window, qtbot)
    dialog.text_input.setPlainText('https://youtu.be/ABC\nhttps://youtu.be/NEW')
    assert 'Уже в списке: 1' in dialog.summary.text()
    qtbot.mouseClick(dialog.accept_button, Qt.MouseButton.LeftButton)
    assert len(window.presenter.repository.list()) == 2


def test_autostart_batch_cancels_optional_probe_without_clearing_draft(make_window, qtbot):
    from tests.support.workbench import HeldProvider

    class Prober(HeldProvider):
        def __init__(self):
            super().__init__()
            self.probe_started = Event()
            self.probe_closed = Event()

        def probe(self, request, context):
            self.probe_started.set()
            try:
                while not context.cancel.wait(0.005):
                    pass
                context.cancel.raise_if_cancelled()
            finally:
                self.probe_closed.set()

    prober = Prober()
    window, _ = make_window(prober)
    window.composer.parameters_button.setChecked(True)
    qtbot.mouseClick(window.auto_start, Qt.MouseButton.LeftButton)
    window.url_input.setText('https://youtu.be/DRAFT')
    qtbot.waitUntil(prober.probe_started.is_set)
    dialog = batch(window, qtbot)
    dialog.text_input.setPlainText('https://youtu.be/NEW')
    qtbot.mouseClick(dialog.accept_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(prober.started.is_set, timeout=2000)
    assert prober.probe_closed.is_set() and window.url_input.text() == 'https://youtu.be/DRAFT'
    assert window.presenter.repository.list()[0].request.link.canonical_id == 'NEW'


def test_audio_and_photo_summary_do_not_advertise_video_quality(make_window, qtbot):
    window, _ = make_window()
    composer = window.composer
    composer.format_box.setCurrentIndex(composer.format_box.findData('mp3'))
    assert 'звук' in composer.summary.text() and not composer.quality_box.isEnabled()
    composer.set_service(Service.INSTAGRAM)
    composer.filter_box.setCurrentIndex(composer.filter_box.findData('photo'))
    assert 'Исходный формат' in composer.summary.text() and not composer.format_box.isEnabled()


def test_auto_start_off_remains_off_after_previous_queue_finishes(make_window, qtbot):
    from clipflow.providers.base import MediaFailure

    class Provider:
        def __init__(self):
            self.calls = 0

        def probe(self, request, context):
            return ProbeResult((), ())

        def execute(self, request, context):
            self.calls += 1
            raise MediaFailure('download_failed')

    provider = Provider()
    window, _ = make_window(provider)
    window.url_input.setText('https://youtu.be/FIRST')
    qtbot.mouseClick(window.add_button, Qt.MouseButton.LeftButton)
    identity = window.presenter.repository.list()[0].id
    window.presenter.toggle_job(identity)
    qtbot.waitUntil(lambda: window.presenter.repository.get(identity).state == JobState.FAILED)
    window.url_input.setText('https://youtu.be/SECOND')
    qtbot.mouseClick(window.add_button, Qt.MouseButton.LeftButton)
    qtbot.wait(1100)
    assert provider.calls == 1 and window.presenter.repository.list()[-1].state == JobState.QUEUED


def test_youtube_numbering_is_off_by_default_persisted_and_mp3_label_is_plain(make_window, qtbot):
    window, _ = make_window()
    composer = window.composer
    composer.set_service(Service.YOUTUBE)
    composer.parameters_button.setChecked(True)
    assert composer.numbering.isVisible() and not composer.numbering.isChecked()
    assert not composer.options().numbering
    assert composer.format_box.itemText(composer.format_box.findData('mp3')) == 'MP3'
    composer.numbering.setChecked(True)
    assert (
        composer.options().numbering
        and window.presenter.settings.presets[Service.YOUTUBE].numbering
    )
    composer.set_service(Service.INSTAGRAM)
    assert not composer.numbering.isVisible()
    composer.set_service(Service.YOUTUBE)
    assert composer.numbering.isChecked()
