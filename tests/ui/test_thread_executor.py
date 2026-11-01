"""The Qt executor: several downloads or one probe, failing callbacks contained, clean close."""

from threading import Event

import pytest

from clipflow.domain.events import WorkFinished
from clipflow.domain.models import ContentKind, Job, Service
from clipflow.infrastructure.executor import ThreadExecutor
from clipflow.providers.base import ProbeResult
from tests.support.scheduler import request


class Provider:
    """Each kind of work waits until the test lets it finish or it is cancelled."""

    def __init__(self):
        self.release = Event()
        self.finished = set()  # downloads let go one by one, by video id
        self.probes = 0

    def _hold(self, context, name=None):
        while not self.release.is_set() and name not in self.finished:
            if context.cancel.wait(0.005):
                context.cancel.raise_if_cancelled()

    def execute(self, request, context):
        self.limiters = [*getattr(self, 'limiters', []), context.limiter]
        self._hold(context, request.link.canonical_id)

    def planned_title(self, request, context):
        self._hold(context)
        return 'Planned name'

    def probe(self, request, context):
        self.probes += 1
        self._hold(context)
        return ProbeResult((), (720,))


@pytest.fixture
def provider():
    return Provider()


@pytest.fixture
def executor(qtbot, provider):
    executor = ThreadExecutor({(Service.YOUTUBE, ContentKind.VIDEO): provider}, auth_gateway=None)
    yield executor
    provider.release.set()
    executor.drain()


def job(name='first'):
    return Job(name, request(name), attempt_id='attempt-' + name)


def failing(*args):
    raise RuntimeError('callback bug')


def test_two_downloads_run_together(executor, provider, qtbot):
    events = {'first': [], 'second': []}
    executor.start(job('first'), events['first'].append)
    executor.start(job('second'), events['second'].append)
    provider.finished.add(request('first').link.canonical_id)
    qtbot.waitUntil(lambda: bool(events['first']))
    assert isinstance(events['first'][-1].payload, WorkFinished)
    assert events['second'] == []
    assert not executor.is_idle
    provider.finished.add(request('second').link.canonical_id)
    qtbot.waitUntil(lambda: executor.is_idle)
    assert isinstance(events['second'][-1].payload, WorkFinished)
    assert provider.limiters == [executor.limiter, executor.limiter]


def test_available_after_each_finish(executor, provider, qtbot):
    signals = []
    executor.available.connect(lambda: signals.append(1))
    executor.start(job('first'), lambda event: None)
    executor.start(job('second'), lambda event: None)
    provider.finished.add(request('first').link.canonical_id)
    qtbot.waitUntil(lambda: len(signals) == 1)
    assert not executor.is_idle


def test_start_refused_while_probing(executor):
    executor.request_probe(request(), 1, lambda *args: None)
    assert executor.probing
    with pytest.raises(ValueError, match='Executor unavailable'):
        executor.start(job(), lambda event: None)


def test_probe_waits_for_all_downloads(executor, provider, qtbot):
    executor.start(job('first'), lambda event: None)
    executor.start(job('second'), lambda event: None)
    executor.request_probe(request(), 1, lambda *args: None)
    assert executor.probing
    provider.finished.add(request('first').link.canonical_id)
    qtbot.waitUntil(lambda: len(executor._workers) == 1)
    qtbot.wait(50)
    assert provider.probes == 0
    provider.finished.add(request('second').link.canonical_id)
    qtbot.waitUntil(lambda: provider.probes == 1)


def test_failing_finish_callback_is_reported_and_the_slot_freed(executor, provider, qtbot):
    errors = []
    executor.error.connect(errors.append)
    executor.start(job(), failing)
    provider.release.set()
    qtbot.waitUntil(lambda: executor.is_idle)
    assert errors == ['queue_update_failed']


def test_failing_title_callback_is_reported(executor, provider, qtbot):
    errors = []
    executor.error.connect(errors.append)
    assert executor.request_title(job(), failing)
    provider.release.set()
    qtbot.waitUntil(lambda: not executor.naming)
    assert errors == ['queue_update_failed']


def test_one_name_lookup_at_a_time(executor):
    assert executor.request_title(job(), lambda *args: None)
    assert not executor.request_title(job('second'), lambda *args: None)


def test_failing_probe_callback_is_reported(executor, provider, qtbot):
    errors = []
    executor.error.connect(errors.append)
    executor.request_probe(request(), 'probe-1', failing)
    provider.release.set()
    qtbot.waitUntil(lambda: executor.is_idle)
    assert errors == ['probe_failed']


def test_no_probe_starts_after_shutdown(executor):
    executor.shutdown()
    executor.request_probe(request(), 'probe-1', lambda *args: None)
    assert executor.is_idle
    assert executor.is_closed


def test_shutdown_stops_a_running_name_lookup(executor, qtbot):
    names = []
    executor.request_title(job(), lambda *args: names.append(args))
    executor.shutdown()
    qtbot.waitUntil(lambda: executor.is_closed)
    assert names == []


def test_failing_cleanup_still_closes_the_executor(qtbot):
    executor = ThreadExecutor({}, None, cleanup=failing)
    errors = []
    executor.error.connect(errors.append)
    executor.shutdown()
    assert executor.is_closed
    assert errors == ['worker_cleanup_failed']


def test_drain_reaps_name_lookup_and_probe_without_delivering_them(executor, provider, qtbot):
    names, probes = [], []
    executor.request_title(job(), lambda *args: names.append(args))
    executor.request_probe(request(), 'probe-1', lambda *args: probes.append(args))
    provider.release.set()
    executor.drain()
    qtbot.wait(50)  # the threads' own finished signals arrive after the reap
    assert executor.is_idle
    assert not executor.naming
    assert executor.is_closed
    assert names == []
    assert probes == []


def test_preferences_set_limiter_rate(executor):
    from clipflow.domain.models import DownloadPreferences

    executor.preferences = DownloadPreferences(rate_limit=2 * 1024 * 1024)
    assert executor.limiter.rate == 2 * 1024 * 1024
    executor.preferences = DownloadPreferences()
    assert executor.limiter.rate is None


def test_download_uses_the_shared_limiter(executor, provider, qtbot):
    executor.start(job(), lambda event: None)
    qtbot.waitUntil(lambda: hasattr(provider, 'limiters'))
    assert provider.limiters == [executor.limiter]
