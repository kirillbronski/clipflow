"""Worker run() rules, exercised synchronously (coverage cannot trace QThread bodies)."""

from pathlib import Path

import pytest

from clipflow.domain.events import (
    ProgressChanged,
    TitleChanged,
    WorkCancelled,
    WorkFailed,
    WorkFinished,
    WorkStopped,
)
from clipflow.domain.models import DownloadOptions, DownloadRequest, Job
from clipflow.domain.urls import parse_url
from clipflow.infrastructure.executor import _ProbeWorker, _TitleWorker, _Worker
from clipflow.providers.base import MediaFailure, ProbeResult


def request(url='https://youtu.be/ABC'):
    return DownloadRequest(parse_url(url), DownloadOptions(Path('/downloads')))


class Provider:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = 0

    def _act(self, context):
        self.calls += 1
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        if callable(self.outcome):
            return self.outcome(context)
        return self.outcome

    def probe(self, request, context):
        return self._act(context)

    def planned_title(self, request, context):
        return self._act(context)

    def execute(self, request, context):
        return self._act(context)


@pytest.mark.parametrize(
    'outcome,error',
    [
        (MediaFailure('auth_required'), 'auth_required'),
        (WorkCancelled('cancel'), 'probe_cancelled'),
        (RuntimeError('secret https://cdn/x'), 'probe_failed'),
    ],
)
def test_probe_worker_maps_failures_to_safe_codes(qapp, outcome, error):
    worker = _ProbeWorker(request(), 'r1', Provider(outcome), None, None, None)
    worker.run()
    assert worker.error == error and worker.heights == ()


def test_probe_worker_reports_distinct_positive_heights_descending(qapp):
    result = ProbeResult((), (720, 1080, 720, 0, -1, '480'))
    worker = _ProbeWorker(request(), 'r1', Provider(result), None, None, None)
    worker.run()
    assert worker.error == '' and worker.heights == (1080, 720)


def test_probe_worker_never_enumerates_collections(qapp):
    provider = Provider(ProbeResult((), (720,)))
    worker = _ProbeWorker(
        request('https://youtube.com/playlist?list=PL_x'), 'r1', provider, None, None, None
    )
    worker.run()
    assert provider.calls == 0 and worker.heights == ()


@pytest.mark.parametrize(
    'outcome,title',
    [('Пропаганда - Мелом', 'Пропаганда - Мелом'), ('   ', None), (MediaFailure('x'), None)],
)
def test_title_worker_keeps_only_usable_names(qapp, outcome, title):
    worker = _TitleWorker(Job('j', request()), Provider(outcome), None, None)
    worker.run()
    assert worker.title == title


@pytest.mark.parametrize(
    'outcome,terminal',
    [
        (None, WorkFinished()),
        (WorkCancelled('pause'), WorkStopped()),
        (MediaFailure('write_failed'), WorkFailed('write_failed')),
        (RuntimeError('secret https://cdn/x'), WorkFailed('worker_failed')),
    ],
)
def test_job_worker_terminal_acknowledgement(qapp, outcome, terminal):
    worker = _Worker(Job('j', request(), attempt_id='a'), Provider(outcome), None, None, None)
    worker.run()
    assert worker.terminal == terminal


def test_job_worker_rejects_terminal_events_from_providers(qapp):
    worker = _Worker(
        Job('j', request(), attempt_id='a'),
        Provider(lambda context: context.emit(WorkFinished())),
        None,
        None,
        None,
    )
    worker.run()
    assert worker.terminal == WorkFailed('invalid_provider_event')


def test_job_worker_throttles_progress_but_not_other_events(qapp):
    def chatty(context):
        for n in range(5):
            context.emit(ProgressChanged(n))
        context.emit(TitleChanged('Name'))

    worker = _Worker(Job('j', request(), attempt_id='a'), Provider(chatty), None, None, None)
    seen = []
    worker.event.connect(seen.append)
    worker.run()
    payloads = [event.payload for event in seen]
    assert payloads == [ProgressChanged(0), TitleChanged('Name')]
    assert all(event.job_id == 'j' and event.attempt_id == 'a' for event in seen)
