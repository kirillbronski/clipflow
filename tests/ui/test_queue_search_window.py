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
