"""Worker bodies as plain functions: safe codes, usable names and terminal acknowledgements."""

from pathlib import Path

import pytest

from clipflow.application.instagram_rate_policy import InstagramDeferred
from clipflow.domain.events import (
    CancellationToken,
    ProgressChanged,
    TitleChanged,
    WorkCancelled,
    WorkFailed,
    WorkFinished,
    WorkStopped,
)
from clipflow.domain.models import DownloadOptions, DownloadRequest
from clipflow.domain.urls import parse_url
from clipflow.infrastructure.work import (
    ProgressThrottle,
    check_provider_event,
    run_download,
    run_probe,
    run_title,
)
from clipflow.providers.base import ExecutionContext, MediaFailure, ProbeResult


def request(url='https://youtu.be/ABC', **options):
    return DownloadRequest(parse_url(url), DownloadOptions(Path('/downloads'), **options))


def context(emit=lambda event: None):
    return ExecutionContext(CancellationToken(), emit, None)


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
        (InstagramDeferred(object()), 'rate_limit'),
        (RuntimeError('secret https://cdn/x'), 'probe_failed'),
    ],
)
def test_probe_maps_failures_to_safe_codes(outcome, error):
    assert run_probe(request(), Provider(outcome), context()) == ((), error)


def test_probe_reports_distinct_positive_heights_descending():
    result = ProbeResult((), (720, 1080, 720, 0, -1, '480'))
    assert run_probe(request(), Provider(result), context()) == ((1080, 720), '')


@pytest.mark.parametrize(
    'probed',
    [
        request('https://youtube.com/playlist?list=PL_x'),
        request(format='mp3'),
        request('https://www.instagram.com/p/ABC/', media_filter='photo'),
    ],
)
def test_probe_never_enumerates_collections_audio_or_photos(probed):
    provider = Provider(ProbeResult((), (720,)))
    assert run_probe(probed, provider, context()) == ((), '')
    assert provider.calls == 0


def test_probe_stops_before_the_site_when_already_cancelled():
    provider = Provider(ProbeResult((), (720,)))
    cancelled = context()
    cancelled.cancel.cancel('cancel')
    assert run_probe(request(), provider, cancelled) == ((), 'probe_cancelled')
    assert provider.calls == 0


@pytest.mark.parametrize(
    'outcome,title',
    [('Пропаганда - Мелом', 'Пропаганда - Мелом'), ('   ', None), (MediaFailure('x'), None)],
)
def test_title_keeps_only_usable_names(outcome, title):
    assert run_title(request(), Provider(outcome), context()) == title


@pytest.mark.parametrize(
    'outcome,terminal',
    [
        (None, WorkFinished()),
        (WorkCancelled('pause'), WorkStopped()),
        (MediaFailure('write_failed'), WorkFailed('write_failed')),
        (RuntimeError('secret https://cdn/x'), WorkFailed('worker_failed')),
    ],
)
def test_download_terminal_acknowledgement(outcome, terminal):
    assert run_download(request(), Provider(outcome), context()) == terminal


def test_download_rejects_terminal_events_from_providers():
    provider = Provider(lambda ctx: ctx.emit(WorkFinished()))
    terminal = run_download(request(), provider, context(check_provider_event))
    assert terminal == WorkFailed('invalid_provider_event')


def test_progress_is_throttled_but_other_events_pass():
    now = [100.0]
    throttle = ProgressThrottle(clock=lambda: now[0])
    assert throttle.allow(ProgressChanged(0))
    now[0] += 0.4
    assert not throttle.allow(ProgressChanged(1))
    assert throttle.allow(TitleChanged('Name'))
    now[0] += 0.1
    assert throttle.allow(ProgressChanged(2))
