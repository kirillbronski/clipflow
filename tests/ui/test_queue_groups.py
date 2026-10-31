"""Playlists and profiles as one row: model, filter, row painting and the group screen."""

from pathlib import Path

from clipflow.domain.events import ProgressChanged
from clipflow.domain.models import DownloadOptions, DownloadRequest, Job, JobState
from clipflow.domain.urls import parse_url
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
