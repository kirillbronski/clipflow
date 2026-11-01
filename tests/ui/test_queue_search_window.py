"""The toolbar, search and sorting in the real window."""

from clipflow.domain.models import DownloadOptions, DownloadRequest, Job, MediaDetails
from clipflow.domain.urls import parse_url
from clipflow.infrastructure.repository import SqliteJobRepository


def test_sorting_does_not_change_download_order(make_window, qtbot, tmp_path):
    repo = SqliteJobRepository(tmp_path / 'order.sqlite3')
    for identity, size in (('first', 300), ('second', 100), ('third', 200)):
        request = DownloadRequest(
            parse_url(f'https://youtu.be/{identity}'), DownloadOptions(tmp_path)
        )
        repo.add(Job(identity, request, details=MediaDetails(size_bytes=size)))
    window, provider = make_window(repository=repo)
    window.proxy.sort_by('size')
    assert [j.id for j in repo.list()] == ['first', 'second', 'third']
    window.presenter.start_queue()
    qtbot.waitUntil(lambda: provider.started.is_set(), timeout=3000)
    assert repo.get('first').state.value in {'probing', 'downloading'}


def seeded(make_window, tmp_path, *specs):
    repo = SqliteJobRepository(tmp_path / 'search.sqlite3')
    for identity, fmt, author in specs:
        options = DownloadOptions(tmp_path, format=fmt)
        request = DownloadRequest(parse_url(f'https://youtu.be/{identity}'), options)
        repo.add(Job(identity, request, details=MediaDetails(author=author)))
    window, _ = make_window(repository=repo)
    return window


def visible(window):
    proxy = window.proxy
    return [proxy.index(r, 0).data(proxy.sourceModel().JobIdRole) for r in range(proxy.rowCount())]


SPECS = (('vid', 'mp4', 'Автор'), ('song', 'mp3', 'Певец'), ('other', 'mp4', 'Ёлкин'))


def test_toolbar_drives_the_list(make_window, tmp_path):
    window = seeded(make_window, tmp_path, *SPECS)
    bar = window.filter_bar
    bar.kind_buttons['audio'].click()
    assert visible(window) == ['song']
    assert bar.items_label.text() == '1 элемент'
    bar.kind_buttons['all'].click()
    bar.open_search()
    bar.search_field.insert('ЕЛКИН')
    assert visible(window) == ['other']
    bar.close_search()
    bar.sort_actions['title'].trigger()
    bar.descending_action.trigger()
    assert sorted(visible(window)) == ['other', 'song', 'vid']  # same titles: queue order
    bar.status_actions['completed'].trigger()
    assert visible(window) == []
    assert bar.status_button.text().startswith('Готово  0')


def test_find_shortcut_focuses_search(make_window, qtbot, tmp_path):
    window = seeded(make_window, tmp_path, *SPECS)
    window.find_action.trigger()
    assert window.filter_bar.search_field.isVisible()
    from PySide6.QtGui import QKeySequence

    assert QKeySequence(QKeySequence.StandardKey.Find) in window.find_action.shortcuts()


def test_nothing_found_message(make_window, tmp_path):
    window = seeded(make_window, tmp_path, *SPECS)
    window.filter_bar.open_search()
    window.filter_bar.search_field.insert('нет такого')
    assert window.empty.isVisible()
    assert window.empty.text() == 'Ничего не найдено'
    window.filter_bar.close_search()
    assert not window.empty.isVisible()


def test_sidebar_keeps_filters(make_window, tmp_path):
    window = seeded(make_window, tmp_path, *SPECS)
    bar = window.filter_bar
    bar.kind_buttons['audio'].click()
    bar.sort_actions['size'].trigger()
    bar.open_search()
    bar.search_field.insert('пев')
    window.nav_buttons[2].click()  # YouTube
    window.nav_buttons[0].click()  # all downloads
    assert window.proxy.kind == 'audio'
    assert window.proxy.sort_key == 'size'
    assert window.proxy.query == 'пев'
    assert bar.search_field.text() == 'пев'
    assert visible(window) == ['song']


def test_hidden_selection_is_dropped(make_window, tmp_path):
    window = seeded(make_window, tmp_path, *SPECS)
    window.queue_view.setCurrentIndex(window.proxy.index(0, 0))  # vid
    window.filter_bar.kind_buttons['audio'].click()
    selected = [
        i.data(window.proxy.sourceModel().JobIdRole)
        for i in window.queue_view.selectionModel().selectedRows()
    ]
    assert 'vid' not in selected


def test_group_screen_uses_the_same_filters(make_window, tmp_path):
    repo = SqliteJobRepository(tmp_path / 'group.sqlite3')
    playlist = DownloadRequest(
        parse_url('https://www.youtube.com/playlist?list=PLgroup'), DownloadOptions(tmp_path)
    )
    repo.add(Job('list', playlist))
    for identity, fmt in (('t1', 'mp3'), ('t2', 'mp4')):
        request = DownloadRequest(
            parse_url(f'https://youtu.be/{identity}'), DownloadOptions(tmp_path, format=fmt)
        )
        repo.add(Job(identity, request, parent_id='list'))
    window, _ = make_window(repository=repo)
    window.queue_panel.open_group('list')
    window.filter_bar.kind_buttons['audio'].click()
    assert visible(window) == ['t1']
    window.queue_panel.close_group()
    assert visible(window) == ['list']


def test_toolbar_fits_narrow_window(make_window, tmp_path):
    window = seeded(make_window, tmp_path, *SPECS)
    window.resize(window.minimumWidth(), 700)
    window.show()
    bar = window.filter_bar
    bar.open_search()
    from PySide6.QtWidgets import QApplication

    QApplication.processEvents()
    assert bar.width() <= window.queue_panel.width()
    right = bar.sort_button.geometry().right()
    assert right <= bar.width()
    last_tab = bar.kind_buttons['playlists'].geometry()
    assert last_tab.right() < bar.status_button.geometry().left()


def test_filters_are_fast_on_2000_jobs(make_window, tmp_path, monkeypatch):
    import time

    from tests.helpers import MemoryJobRepository

    repo = MemoryJobRepository()
    for n in range(2000):
        fmt = 'mp3' if n % 3 == 0 else 'mp4'
        request = DownloadRequest(
            parse_url(f'https://youtu.be/id{n:05d}'), DownloadOptions(tmp_path, format=fmt)
        )
        repo.add(
            Job(str(n), request, details=MediaDetails(size_bytes=n + 1, duration=float(n + 1)))
        )
    window, _ = make_window(repository=repo)
    reads = []
    original = repo.list
    monkeypatch.setattr(repo, 'list', lambda *a, **k: reads.append(1) or original(*a, **k))
    bar = window.filter_bar
    for action in (
        lambda: bar.kind_buttons['audio'].click(),
        lambda: (bar.open_search(), bar.search_field.insert('id0')),
        lambda: bar.sort_actions['size'].trigger(),
        lambda: bar.descending_action.trigger(),
    ):
        start = time.perf_counter()
        action()
        assert time.perf_counter() - start < 0.5
    assert reads == []


def playlist_window(make_window, tmp_path, tracks=700, title='Лекции по физике'):
    from tests.helpers import MemoryJobRepository

    repo = MemoryJobRepository()
    playlist = DownloadRequest(
        parse_url('https://www.youtube.com/playlist?list=PLgroup'), DownloadOptions(tmp_path)
    )
    repo.add(Job('list', playlist, title=title))
    for n in range(tracks):
        request = DownloadRequest(
            parse_url(f'https://youtu.be/t{n:05d}'), DownloadOptions(tmp_path)
        )
        details = MediaDetails(size_bytes=n + 1, duration=float(n + 1))
        repo.add(Job(f't{n:05d}', request, parent_id='list', title=f'Трек {n}', details=details))
    window, _ = make_window(repository=repo)
    return window, repo


def test_long_playlist_stop_all_stays_fast_with_search_and_sort(make_window, qtbot, tmp_path):
    import time

    from PySide6.QtWidgets import QApplication

    from clipflow.domain.models import JobState

    window, repo = playlist_window(make_window, tmp_path)
    bar = window.filter_bar
    bar.sort_actions['size'].trigger()
    bar.open_search()
    bar.search_field.insert('трек 699')  # only the last track matches
    QApplication.processEvents()
    start = time.perf_counter()
    window.presenter.cancel_queue()
    qtbot.waitUntil(lambda: all(j.state == JobState.CANCELLED for j in repo.list()), timeout=60000)
    QApplication.processEvents()
    assert time.perf_counter() - start < 0.4


def test_playlist_found_by_name_shows_its_tracks(make_window, tmp_path):
    window, _ = playlist_window(make_window, tmp_path, tracks=3)
    bar = window.filter_bar
    bar.open_search()
    bar.search_field.insert('лекции')
    assert visible(window) == ['list']
    window.queue_panel.open_group('list')
    assert visible(window) == ['t00000', 't00001', 't00002']
    bar.search_field.clear()
    bar.search_field.insert('трек 1')
    assert visible(window) == ['t00001']


def test_search_fits_minimum_width_in_russian(make_window, tmp_path):
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QApplication

    window = seeded(make_window, tmp_path, *SPECS)
    window.resize(window.minimumWidth(), 700)
    bar = window.filter_bar
    for _ in range(2):
        bar.open_search()
        QApplication.processEvents()
        edge = bar.sort_button.mapTo(window, QPoint(bar.sort_button.width(), 0)).x()
        assert edge <= window.width()
        assert not bar.items_label.isVisible()
        bar.close_search()
        QApplication.processEvents()
        assert bar.items_label.isVisible()
        edge = bar.sort_button.mapTo(window, QPoint(bar.sort_button.width(), 0)).x()
        assert edge <= window.width()


def test_enter_after_filter_does_not_toggle_a_neighbour(make_window, qtbot, tmp_path, monkeypatch):
    from PySide6.QtCore import Qt

    window = seeded(make_window, tmp_path, *SPECS)
    toggled = []
    monkeypatch.setattr(window.presenter, 'toggle_job', toggled.append)
    window.queue_view.setCurrentIndex(window.proxy.index(0, 0))  # vid
    window.filter_bar.kind_buttons['audio'].click()
    window.queue_view.setFocus()
    qtbot.keyClick(window.queue_view, Qt.Key.Key_Return)
    assert toggled == []


def test_empty_text_follows_status_and_empty_queue(make_window, tmp_path):
    window = seeded(make_window, tmp_path, *SPECS)
    window.filter_bar.status_actions['failed'].trigger()
    assert window.empty.isVisible()
    assert window.empty.text() == 'Ничего не найдено'
    empty_window, _ = make_window()
    empty_window.filter_bar.kind_buttons['video'].click()
    assert empty_window.empty.text() == empty_window.tr.text('empty')
