"""The .m3u8 list is written when a playlist finishes and goes with its files."""

from dataclasses import replace

from clipflow.domain.events import JobEvent, WorkFinished
from clipflow.domain.models import (
    DownloadOptions,
    DownloadRequest,
    Job,
    JobState,
    MediaDetails,
    PlaylistPosition,
)
from clipflow.domain.urls import parse_url
from clipflow.infrastructure.repository import SqliteJobRepository

PLAYLIST = 'https://www.youtube.com/playlist?list=PLm3u'


def playlist(make_window, tmp_path, states=(JobState.COMPLETED, JobState.COMPLETED), m3u=True):
    root = tmp_path / 'downloads'
    folder = root / 'Мой плейлист'
    folder.mkdir(parents=True)
    repo = SqliteJobRepository(tmp_path / 'm3u.sqlite3')
    parent = Job(
        'list',
        DownloadRequest(parse_url(PLAYLIST), DownloadOptions(root)),
        state=JobState.COMPLETED,
        title='Мой плейлист',
    )
    repo.add(parent)
    for n, state in enumerate(states, 1):
        media = folder / f'{n:02d} Трек {n}.mp4'
        files = ()
        if state == JobState.COMPLETED:
            media.write_bytes(b'x')
            files = (media,)
        request = DownloadRequest(
            parse_url(f'https://www.youtube.com/watch?v=track{n}'),
            DownloadOptions(root),
            playlist=PlaylistPosition('PLm3u', n, 'Мой плейлист'),
        )
        repo.add(
            Job(
                f't{n}',
                request,
                state=state,
                parent_id='list',
                result_files=files,
                details=MediaDetails(duration=60.0 * n),
            )
        )
    window, _ = make_window(repository=repo)
    window.presenter.update_preferences(playlist_m3u=m3u)
    return window, repo, folder / 'Мой плейлист.m3u8'


def finish(window, identity):
    window.presenter._on_event(JobEvent(identity, '', WorkFinished()))


def test_m3u_written_when_playlist_finishes(make_window, tmp_path):
    window, _, m3u = playlist(make_window, tmp_path)
    finish(window, 't2')
    assert m3u.read_text(encoding='utf-8') == (
        '#EXTM3U\n#EXTINF:60,01 Трек 1\n01 Трек 1.mp4\n#EXTINF:120,02 Трек 2\n02 Трек 2.mp4\n'
    )


def test_no_m3u_while_tracks_are_left(make_window, tmp_path):
    window, _, m3u = playlist(make_window, tmp_path, (JobState.COMPLETED, JobState.QUEUED))
    finish(window, 't1')
    assert not m3u.exists()


def test_m3u_rewritten_after_retry(make_window, tmp_path):
    window, repo, m3u = playlist(make_window, tmp_path, (JobState.COMPLETED, JobState.FAILED))
    finish(window, 't1')
    assert '02 Трек 2' not in m3u.read_text(encoding='utf-8')
    media = m3u.parent / '02 Трек 2.mp4'
    media.write_bytes(b'x')
    repo.update(replace(repo.get('t2'), state=JobState.COMPLETED, result_files=(media,)))
    finish(window, 't2')
    text = m3u.read_text(encoding='utf-8')
    assert text.count('02 Трек 2.mp4') == 1
    assert text.count('01 Трек 1.mp4') == 1


def test_no_m3u_when_off(make_window, tmp_path):
    window, _, m3u = playlist(make_window, tmp_path, m3u=False)
    finish(window, 't2')
    assert not m3u.exists()


def test_deleting_group_files_removes_m3u(make_window, tmp_path, qtbot):
    window, _, m3u = playlist(make_window, tmp_path)
    finish(window, 't2')
    assert m3u.exists()
    window.presenter.delete_group_files('list', confirmed=True)
    qtbot.waitUntil(lambda: not m3u.exists(), timeout=3000)
    assert not m3u.parent.exists()


def test_progress_does_not_rebuild_m3u(make_window, tmp_path, monkeypatch):
    from clipflow.domain.events import ProgressChanged

    window, _, _ = playlist(make_window, tmp_path, (JobState.COMPLETED, JobState.DOWNLOADING))
    plans = []
    original = window.presenter._m3u_plan
    monkeypatch.setattr(window.presenter, '_m3u_plan', lambda g: plans.append(g) or original(g))
    for _ in range(20):
        window.presenter._on_event(JobEvent('t2', '', ProgressChanged(1, 10, 1.0, 1.0)))
    assert plans == []


def test_refused_deletion_keeps_m3u(make_window, tmp_path, monkeypatch):
    from clipflow.ui.presenter_clearing import ClearingController

    window, _, m3u = playlist(make_window, tmp_path)
    finish(window, 't2')
    monkeypatch.setattr(ClearingController, '_idle', property(lambda self: False))
    window.presenter.delete_group_files('list', confirmed=True)
    assert m3u.exists()
    assert (m3u.parent / '01 Трек 1.mp4').exists()


def test_removing_a_track_rewrites_m3u(make_window, tmp_path):
    window, _, m3u = playlist(make_window, tmp_path)
    finish(window, 't2')
    window.presenter.remove_jobs(['t2'])
    assert '02 Трек 2' not in m3u.read_text(encoding='utf-8')
    assert '01 Трек 1.mp4' in m3u.read_text(encoding='utf-8')


def test_deleting_a_track_file_rewrites_m3u(make_window, tmp_path):
    window, _, m3u = playlist(make_window, tmp_path)
    finish(window, 't2')
    window.presenter.delete_files(['t1'], confirmed=True)
    text = m3u.read_text(encoding='utf-8')
    assert '01 Трек 1' not in text
    assert '02 Трек 2.mp4' in text


def test_turning_the_setting_on_writes_finished_playlists(make_window, tmp_path):
    window, _, m3u = playlist(make_window, tmp_path, m3u=False)
    finish(window, 't2')
    assert not m3u.exists()
    window.presenter.update_preferences(playlist_m3u=True)
    assert '02 Трек 2.mp4' in m3u.read_text(encoding='utf-8')


def test_cancelling_the_last_tracks_writes_m3u(make_window, tmp_path):
    window, _, m3u = playlist(make_window, tmp_path, (JobState.COMPLETED, JobState.QUEUED))
    window.presenter.cancel_queue()  # «Остановить всё»: what was downloaded still gets a list
    assert '01 Трек 1.mp4' in m3u.read_text(encoding='utf-8')


def test_deleting_group_files_removes_m3u_of_files_already_gone(make_window, tmp_path, qtbot):
    window, _, m3u = playlist(make_window, tmp_path)
    finish(window, 't2')
    for media in m3u.parent.glob('*.mp4'):
        media.unlink()
    window.presenter.delete_group_files('list', confirmed=True)
    qtbot.waitUntil(lambda: not m3u.exists(), timeout=3000)
