"""A system notification when the queue has finished its run."""

from datetime import UTC, datetime, timedelta

import pytest

from clipflow.domain.events import JobEvent, WorkFailed, WorkFinished, WorkStopped
from clipflow.domain.models import DownloadOptions, DownloadRequest, Job, JobState
from clipflow.domain.urls import parse_url
from clipflow.infrastructure.repository import SqliteJobRepository


def queue(make_window, tmp_path, states, notify=True, monkeypatch=None):
    repo = SqliteJobRepository(tmp_path / 'notify.sqlite3')
    for n, state in enumerate(states):
        request = DownloadRequest(parse_url(f'https://youtu.be/note{n}'), DownloadOptions(tmp_path))
        extra = {}
        if state == 'rate':
            state = JobState.PAUSED
            extra = {
                'automatic_retry': True,
                'pause_reason': 'rate_limit',
                'next_allowed_at': datetime.now(UTC) + timedelta(minutes=5),
            }
        if state == JobState.COMPLETED:
            media = tmp_path / f'note{n}.mp4'
            media.write_bytes(b'x')
            extra = {'result_files': (media,)}
        repo.add(Job(f'j{n}', request, state=state, **extra))
    window, _ = make_window(repository=repo)
    window.presenter.update_preferences(notify_done=notify)
    shown = []
    monkeypatch.setattr(
        window.notifier, 'showMessage', lambda title, text, *args: shown.append((title, text))
    )
    return window, shown


def events(window, *pairs):
    for identity, payload in pairs:
        window.presenter._on_event(JobEvent(identity, '', payload))
    window.presenter._tick()


def test_finished_run_notifies_once(make_window, tmp_path, monkeypatch):
    states = [JobState.COMPLETED] * 3 + [JobState.FAILED]
    window, shown = queue(make_window, tmp_path, states, monkeypatch=monkeypatch)
    events(
        window,
        ('j0', WorkFinished()),
        ('j1', WorkFinished()),
        ('j2', WorkFinished()),
        ('j3', WorkFailed('network')),
    )
    assert shown == [('ClipFlow — загрузки завершены', 'Скачано: 3, с ошибкой: 1')]
    window.presenter._tick()
    assert len(shown) == 1


def test_only_cancelled_does_not_notify(make_window, tmp_path, monkeypatch):
    window, shown = queue(make_window, tmp_path, [JobState.CANCELLED], monkeypatch=monkeypatch)
    events(window, ('j0', WorkStopped()))
    assert shown == []


def test_rate_limit_pause_is_not_finished(make_window, tmp_path, monkeypatch):
    window, shown = queue(
        make_window, tmp_path, [JobState.COMPLETED, 'rate'], monkeypatch=monkeypatch
    )
    events(window, ('j0', WorkFinished()))
    assert shown == []


def test_notify_off_is_silent(make_window, tmp_path, monkeypatch):
    window, shown = queue(
        make_window, tmp_path, [JobState.COMPLETED], notify=False, monkeypatch=monkeypatch
    )
    events(window, ('j0', WorkFinished()))
    assert shown == []


@pytest.mark.parametrize(('language', 'text'), [('en', 'Downloaded: 1')])
def test_texts_follow_language(make_window, tmp_path, monkeypatch, language, text):
    window, shown = queue(make_window, tmp_path, [JobState.COMPLETED], monkeypatch=monkeypatch)
    window.presenter.update_preferences(language=language)
    events(window, ('j0', WorkFinished()))
    assert shown == [('ClipFlow — downloads finished', text)]


def test_playlist_listing_is_not_a_download(make_window, tmp_path, monkeypatch):
    repo = SqliteJobRepository(tmp_path / 'list.sqlite3')
    playlist = DownloadRequest(
        parse_url('https://www.youtube.com/playlist?list=PLnote'), DownloadOptions(tmp_path)
    )
    repo.add(Job('list', playlist, state=JobState.COMPLETED))
    media = tmp_path / 'a.mp4'
    media.write_bytes(b'x')
    track = DownloadRequest(parse_url('https://youtu.be/track'), DownloadOptions(tmp_path))
    repo.add(Job('t', track, state=JobState.COMPLETED, parent_id='list', result_files=(media,)))
    window, _ = make_window(repository=repo)
    window.presenter.update_preferences(notify_done=True)
    shown = []
    monkeypatch.setattr(
        window.notifier, 'showMessage', lambda title, text, *args: shown.append(text)
    )
    events(window, ('list', WorkFinished()), ('t', WorkFinished()))
    assert shown == ['Скачано: 1']
