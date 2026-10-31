"""Playlists and profiles as one row: model, filter, row painting and the group screen."""

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt

from clipflow.domain.events import ProgressChanged
from clipflow.domain.models import DownloadOptions, DownloadRequest, Job, JobState
from clipflow.domain.urls import parse_url
from clipflow.ui.i18n import Translator
from clipflow.ui.job_status import group_text
from clipflow.ui.queue_delegate import QueueDelegate
from clipflow.ui.queue_model import JobListModel, QueueFilter

PLAYLIST = 'https://www.youtube.com/playlist?list=PLgroup'


def job(identity, parent=None, state=JobState.QUEUED, url=None, files=(), folder=None):
    link = parse_url(url or 'https://youtu.be/' + identity)
    request = DownloadRequest(link, DownloadOptions(folder or Path('/downloads')))
    return Job(identity, request, state=state, parent_id=parent, result_files=files)


def playlist(tmp_path, size=3):
    media = tmp_path / 'a.mp4'
    media.write_bytes(b'12345')
    members = [job('c0', 'p', JobState.COMPLETED, files=(media,), folder=tmp_path)]
    members += [job(f'c{n}', 'p') for n in range(1, size)]
    return [job('p', url=PLAYLIST, state=JobState.COMPLETED), *members]


def test_group_row_carries_its_summary(qapp, tmp_path):
    model = JobListModel(playlist(tmp_path))
    summary = model.index(0).data(JobListModel.GroupRole)
    assert (summary.total, summary.completed, summary.size_bytes) == (3, 1, 5)
    assert model.index(1).data(JobListModel.GroupRole) is None
    assert model.members('p')[0].id == 'c0'
    assert model.is_group_row(0)
    assert not model.is_group_row(1)


def test_child_progress_repaints_the_group_row(qapp, tmp_path):
    jobs = playlist(tmp_path)
    model = JobListModel(jobs)
    rows = []
    model.dataChanged.connect(lambda first, last: rows.extend(range(first.row(), last.row() + 1)))
    model.update_job(jobs[2], ProgressChanged(10, 100))
    assert 0 in rows
    assert 2 in rows


def test_file_sizes_are_read_once(qapp, tmp_path, monkeypatch):
    model = JobListModel(playlist(tmp_path))
    calls = []
    original = Path.stat
    monkeypatch.setattr(Path, 'stat', lambda self, **kw: calls.append(self) or original(self, **kw))
    for _ in range(3):
        model.index(0).data(JobListModel.GroupRole)
    assert len(calls) <= 1


def test_missing_files_count_as_nothing(qapp, tmp_path):
    jobs = playlist(tmp_path)
    (tmp_path / 'a.mp4').unlink()
    model = JobListModel(jobs)
    assert model.index(0).data(JobListModel.GroupRole).size_bytes == 0


def big_playlist(done=70, failed=2, queued=4):
    states = [JobState.COMPLETED] * done + [JobState.FAILED] * failed + [JobState.QUEUED] * queued
    members = [job(f'c{n:02d}', 'p', state) for n, state in enumerate(states)]
    return [job('p', url=PLAYLIST, state=JobState.COMPLETED), *members, job('single')]


def test_a_playlist_of_76_is_one_row(qapp):
    proxy = QueueFilter(JobListModel(big_playlist()))
    assert proxy.rowCount() == 2
    assert proxy.group_id is None


def test_group_screen_lists_only_its_members(qapp):
    proxy = QueueFilter(JobListModel(big_playlist()))
    proxy.show_group('p')
    assert proxy.rowCount() == 76
    rows = [proxy.index(n, 0).data(JobListModel.JobRole) for n in range(76)]
    assert {r.parent_id for r in rows} == {'p'}
    proxy.show_group(None)
    assert proxy.rowCount() == 2


def test_status_tabs_follow_group_content(qapp):
    proxy = QueueFilter(JobListModel(big_playlist()))
    ids = lambda: [proxy.index(n, 0).data(JobListModel.JobIdRole) for n in range(proxy.rowCount())]  # noqa: E731
    for status in ('active', 'completed', 'failed'):
        proxy.show_status(status)
        assert 'p' in ids()
    proxy.show_status('failed')
    assert 'single' not in ids()
    proxy.show_group('p')
    assert proxy.rowCount() == 2
    proxy.show_status('completed')
    assert proxy.rowCount() == 70


def test_group_without_members_filters_by_its_parent(qapp):
    proxy = QueueFilter(JobListModel([job('p', url=PLAYLIST, state=JobState.FAILED)]))
    for status, visible in (('all', 1), ('failed', 1), ('active', 0), ('completed', 0)):
        proxy.show_status(status)
        assert proxy.rowCount() == visible


def test_history_shows_a_group_with_finished_members(qapp):
    proxy = QueueFilter(JobListModel(big_playlist(done=1, failed=0, queued=3)))
    proxy.show_source(history=True)
    assert [proxy.index(0, 0).data(JobListModel.JobIdRole)] == ['p']


PROFILE = 'https://www.instagram.com/someone/'


def summary(parent_state=JobState.COMPLETED, url=PLAYLIST, **counts):
    from clipflow.application.groups import GroupSummary

    values = dict(total=76, completed=40, failed=0, active=0, size_bytes=0, current=None)
    values.update(counts)
    parent = replace(job('p', url=url, state=parent_state), error='youtube_unavailable')
    return GroupSummary(parent=parent, **values)


def test_group_text_variants(qapp):
    tr = Translator('ru')
    gb = int(4.3 * 1024**3)
    assert group_text(summary(size_bytes=gb), tr) == '76 видео  ·  скачано 40  ·  4,3 ГБ'
    assert group_text(summary(completed=70, failed=6, size_bytes=5 * 1024**2), tr) == (
        '76 видео  ·  скачано 70  ·  6 с ошибкой  ·  5,0 МБ'
    )
    working = summary(active=36, current=job('c1', 'p', JobState.DOWNLOADING))
    assert group_text(working, tr, title='Урок 5', percent=35) == (
        'скачано 40 из 76  ·  сейчас: Урок 5  ·  35%'
    )
    assert group_text(working, tr, title='Урок 5') == 'скачано 40 из 76  ·  сейчас: Урок 5'
    failed = summary(JobState.FAILED, total=0, completed=0)
    assert group_text(failed, tr).startswith('Не удалось получить список  ·  ')
    assert group_text(summary(JobState.PROBING, total=0, completed=0), tr) is None
    assert group_text(summary(url=PROFILE, total=12, completed=12), tr) == (
        '12 постов  ·  скачано 12'
    )
    assert group_text(summary(url=PROFILE, total=1, completed=0), tr) == '1 пост  ·  скачано 0'
    en = Translator('en')
    assert group_text(summary(total=1, completed=1), en) == '1 video  ·  1 downloaded'


def test_group_row_buttons_emit_actions(qapp, tmp_path):
    from PySide6.QtCore import QEvent, QPointF, QRect
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QStyleOptionViewItem

    model = JobListModel(playlist(tmp_path))
    delegate = QueueDelegate()
    seen = []
    delegate.action_requested.connect(lambda *args: seen.append(args))
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 800, 96)
    for button in delegate._group_buttons(option.rect.adjusted(0, 0, -2, 0)):
        point = QPointF(button.center())
        event = QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            point,
            point,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        delegate.editorEvent(event, model, option, model.index(0))
    assert seen == [('p', 'group_folder'), ('p', 'group_menu'), ('p', 'open_group')]


def window_with_playlist(make_window, singles=30, members=76):
    window, _ = make_window()
    repository = window.presenter.repository
    repository.add(job('p', url=PLAYLIST, state=JobState.COMPLETED))
    for n in range(members):
        repository.add(job(f'c{n:02d}', 'p', JobState.COMPLETED))
    for n in range(singles):
        repository.add(job(f's{n:02d}', state=JobState.COMPLETED))
    window.presenter._reload_jobs()
    window.resize(1000, 700)
    return window


def group_index(window):
    proxy = window.queue_panel.proxy
    return next(
        proxy.index(n, 0)
        for n in range(proxy.rowCount())
        if proxy.index(n, 0).data(JobListModel.JobIdRole) == 'p'
    )


def test_open_and_back_restore_the_list(make_window, qtbot):
    window = window_with_playlist(make_window)
    panel, view = window.queue_panel, window.queue_view
    qtbot.waitUntil(lambda: view.verticalScrollBar().maximum() > 0)
    view.setCurrentIndex(panel.proxy.index(5, 0))
    view.verticalScrollBar().setValue(view.verticalScrollBar().maximum())
    scroll = view.verticalScrollBar().value()
    window._row_action('p', 'open_group')
    assert panel.group_id == 'p'
    assert panel.group_bar.isVisibleTo(window)
    assert panel.proxy.rowCount() == 76
    panel.back_button.click()
    assert panel.group_id is None
    assert not panel.group_bar.isVisibleTo(window)
    assert panel.proxy.rowCount() == 31
    qtbot.waitUntil(lambda: view.verticalScrollBar().value() == scroll)
    assert view.currentIndex().row() == 5


def test_escape_returns_from_a_group(make_window, qtbot):
    window = window_with_playlist(make_window, singles=1)
    window.queue_panel.open_group('p')
    qtbot.keyClick(window.queue_view, Qt.Key.Key_Escape)
    assert window.queue_panel.group_id is None


def test_activating_a_group_row_opens_it(make_window):
    window = window_with_playlist(make_window, singles=1)
    window.queue_view.activated.emit(group_index(window))
    assert window.queue_panel.group_id == 'p'
    assert window.presenter.repository.get('p').state == JobState.COMPLETED


def test_screen_returns_when_its_group_disappears(make_window, qtbot):
    window = window_with_playlist(make_window, singles=1)
    window.queue_panel.open_group('p')
    window.presenter.clear_all()
    qtbot.waitUntil(lambda: window.queue_panel.group_id is None)


def test_counts_follow_the_screen(make_window, qtbot):
    window = window_with_playlist(make_window, singles=1)
    panel = window.queue_panel
    qtbot.waitUntil(lambda: ' 2 ' in panel.count_label.text() + ' ')
    assert panel.status_buttons['all'].text().endswith(' 2')
    panel.open_group('p')
    qtbot.waitUntil(lambda: '76' in panel.count_label.text())
    assert panel.status_buttons['all'].text().endswith(' 76')
    assert panel.group_title.text() == window.presenter.model.index(0).data(JobListModel.TitleRole)
    assert panel.group_details.text() == '76 видео'


def member_states(window):
    return [window.presenter.repository.get(f'c{n:02d}').state for n in range(5)]


def test_group_pause_and_resume_cover_all_members(make_window):
    window, _ = make_window()
    repository = window.presenter.repository
    repository.add(job('p', url=PLAYLIST, state=JobState.COMPLETED))
    for n in range(5):
        repository.add(job(f'c{n:02d}', 'p'))
    window.presenter._reload_jobs()
    window.presenter.pause_group('p')
    assert member_states(window) == [JobState.PAUSED] * 5
    window.presenter.resume_group('p')
    assert JobState.PAUSED not in member_states(window)


def test_retry_failures_only_touches_failed_members(make_window):
    window, _ = make_window()
    repository = window.presenter.repository
    repository.add(job('p', url=PLAYLIST, state=JobState.COMPLETED))
    repository.add(job('c00', 'p', JobState.FAILED))
    repository.add(job('c01', 'p', JobState.CANCELLED))
    repository.add(job('c02', 'p', JobState.COMPLETED))
    window.presenter._reload_jobs()
    window.presenter.retry_group_failures('p')
    states = [repository.get(i).state for i in ('c00', 'c01', 'c02')]
    assert JobState.FAILED not in states[:2]
    assert JobState.CANCELLED not in states[:2]
    assert states[2] == JobState.COMPLETED


def files_playlist(window, tmp_path):
    root = tmp_path / 'downloads'
    folder = root / 'YouTube' / 'Плейлист [PLgroup]'
    folder.mkdir(parents=True)
    repository = window.presenter.repository
    repository.add(job('p', url=PLAYLIST, state=JobState.COMPLETED, folder=root))
    for n in range(2):
        media = folder / f'{n:03d} - track.mp3'
        media.write_bytes(b'audio')
        repository.add(job(f'c{n:02d}', 'p', JobState.COMPLETED, files=(media,), folder=root))
    window.presenter._reload_jobs()
    return root, folder


def test_group_folder_is_the_common_folder(make_window, tmp_path, monkeypatch):
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices

    window, _ = make_window()
    _, folder = files_playlist(window, tmp_path)
    opened = []
    monkeypatch.setattr(QDesktopServices, 'openUrl', lambda url: opened.append(url) or True)
    window._row_action('p', 'group_folder')
    assert opened == [QUrl.fromLocalFile(str(folder))]


def test_remove_group_takes_its_members_and_keeps_files(make_window, tmp_path, qtbot):
    window, _ = make_window()
    _, folder = files_playlist(window, tmp_path)
    window.presenter.repository.add(job('single'))
    window.presenter._reload_jobs()
    window.presenter.remove_group('p')
    qtbot.waitUntil(lambda: [j.id for j in window.presenter.repository.list()] == ['single'])
    assert len(list(folder.iterdir())) == 2


def test_delete_group_files_needs_confirmation(make_window, tmp_path):
    window, _ = make_window()
    root, folder = files_playlist(window, tmp_path)
    window.presenter.delete_group_files('p')
    assert len(list(folder.iterdir())) == 2
    window.presenter.delete_group_files('p', confirmed=True)
    assert not folder.exists()
    assert root.is_dir()
    assert len(window.presenter.repository.list()) == 3


def test_context_menu_on_a_group_acts_on_the_whole_group(make_window, tmp_path, qtbot):
    from PySide6.QtCore import QItemSelectionModel
    from PySide6.QtWidgets import QMenu

    window, _ = make_window()
    files_playlist(window, tmp_path)
    window.presenter.repository.add(job('single', state=JobState.COMPLETED))
    window.presenter._reload_jobs()
    view = window.queue_view
    selection = view.selectionModel()
    for row in range(view.model().rowCount()):
        selection.select(view.model().index(row, 0), QItemSelectionModel.SelectionFlag.Select)
    window._history_menu(view.visualRect(group_index(window)).center())
    menu = window.findChildren(QMenu)[-1]
    texts = [a.text() for a in menu.actions()]
    assert window.tr.text('group_menu.retry_failed') in texts
    remove = next(a for a in menu.actions() if a.text() == window.tr.text('group_menu.remove'))
    remove.trigger()
    qtbot.waitUntil(lambda: [j.id for j in window.presenter.repository.list()] == ['single'])


def test_group_actions_read_a_long_queue_a_fixed_number_of_times(make_window):
    window, _ = make_window()
    repository = window.presenter.repository
    repository.add(job('p', url=PLAYLIST, state=JobState.COMPLETED))
    for n in range(700):
        repository.add(job(f'c{n:03d}', 'p', JobState.FAILED))
    window.presenter._reload_jobs()
    reads = []
    original = repository.list
    repository.list = lambda: reads.append(1) or original()
    for action in ('pause_group', 'resume_group', 'retry_group_failures'):
        reads.clear()
        getattr(window.presenter, action)('p')
        assert len(reads) <= 4, action


def test_menu_button_offers_what_the_group_allows(make_window, tmp_path):
    from PySide6.QtWidgets import QMenu

    window, _ = make_window()
    files_playlist(window, tmp_path)
    window._row_action('p', 'group_menu')
    menu = window.findChildren(QMenu)[-1]
    enabled = {a.text(): a.isEnabled() for a in menu.actions() if a.text()}
    assert enabled == {
        'Приостановить все': False,
        'Продолжить все': False,
        'Повторить неудачные': False,
        'Открыть папку': True,
        'Убрать из списка': True,
        'Удалить файлы с диска…': True,
    }
