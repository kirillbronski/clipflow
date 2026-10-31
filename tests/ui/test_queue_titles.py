"""Queued rows show a name at once and the future file name after a paced background lookup."""

import time

from clipflow.domain.models import DownloadOptions, DownloadRequest, Job, JobState
from clipflow.domain.urls import parse_url
from clipflow.infrastructure.repository import SqliteJobRepository
from clipflow.providers.base import MediaFailure
from tests.support.workbench import HeldProvider


class Naming(HeldProvider):
    def __init__(self, names):
        super().__init__()
        self.names = names
        self.calls = []
        self.active = 0
        self.overlap = False

    def planned_title(self, request, context):
        self.active += 1
        self.overlap = self.overlap or self.active > 1
        self.calls.append((request.link.canonical_id, time.monotonic()))
        try:
            time.sleep(0.02)
            name = self.names.get(request.link.canonical_id)
            if name is None:
                raise MediaFailure('probe_failed')
            return name
        finally:
            self.active -= 1


def title(window, identity):
    model = window.presenter.model
    return model.data(model.index(model._rows[identity]))


def test_labels_show_at_once_then_paced_lookup_names_waiting_videos(make_window, qtbot, tmp_path):
    repo = SqliteJobRepository(tmp_path / 'titles.sqlite3')

    def job(identity, video, label, state=JobState.QUEUED):
        request = DownloadRequest(
            parse_url(f'https://music.youtube.com/watch?v={video}'),
            DownloadOptions(tmp_path),
            label=label,
        )
        repo.add(Job(identity, request, state=state))

    job('a', 'track_A', 'Мелом')
    job('b', 'track_B', 'Между Мной')
    job('c', 'track_C', 'Готово', JobState.COMPLETED)
    job('d', 'track_D', 'Пауза', JobState.PAUSED)
    provider = Naming(
        {
            'track_A': 'Пропаганда - Мелом',
            'track_D': 'Дыши - Взгляни на небо',
            'track_C': 'не нужно',
        }
    )
    window, _ = make_window(provider, repo)
    window.presenter.title_interval_ms = 150
    assert title(window, 'a') == 'Мелом' and title(window, 'b') == 'Между Мной'
    qtbot.waitUntil(lambda: len(provider.calls) >= 3, timeout=5000)
    qtbot.waitUntil(lambda: title(window, 'd') == 'Дыши - Взгляни на небо', timeout=5000)
    assert title(window, 'a') == 'Пропаганда - Мелом' and title(window, 'b') == 'Между Мной'
    assert repo.get('a').title == 'Пропаганда - Мелом' and repo.get('b').title is None
    called = [identity for identity, _ in provider.calls]
    assert sorted(called) == ['track_A', 'track_B', 'track_D'] and not provider.overlap
    gaps = [b - a for (_, a), (_, b) in zip(provider.calls, provider.calls[1:], strict=False)]
    assert all(gap >= 0.14 for gap in gaps)
    qtbot.wait(400)
    assert len(provider.calls) == 3  # a failed lookup is not retried in a loop


def test_providers_without_lookup_are_skipped(make_window, qtbot, tmp_path):
    repo = SqliteJobRepository(tmp_path / 'plain.sqlite3')
    repo.add(
        Job(
            'a',
            DownloadRequest(
                parse_url('https://youtu.be/track_A'), DownloadOptions(tmp_path), label='Ролик'
            ),
        )
    )
    window, provider = make_window(None, repo)
    window.presenter.title_interval_ms = 50
    qtbot.wait(300)
    assert title(window, 'a') == 'Ролик' and repo.get('a').title is None
