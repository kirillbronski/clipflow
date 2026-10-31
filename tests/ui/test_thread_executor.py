"""The Qt executor: one download or probe at a time, failing callbacks contained, clean close."""

from threading import Event

import pytest

from clipflow.domain.models import ContentKind, Job, Service
from clipflow.infrastructure.executor import ThreadExecutor
from clipflow.providers.base import ProbeResult
from tests.support.scheduler import request


class Provider:
    """Each kind of work waits until the test lets it finish or it is cancelled."""

    def __init__(self):
        self.release = Event()

    def _hold(self, context):
        while not self.release.is_set():
            if context.cancel.wait(0.005):
                context.cancel.raise_if_cancelled()

    def execute(self, request, context):
        self._hold(context)

    def planned_title(self, request, context):
        self._hold(context)
        return 'Planned name'

    def probe(self, request, context):
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


def test_second_download_is_refused_while_one_runs(executor):
    executor.start(job(), lambda event: None)
    with pytest.raises(ValueError, match='Executor unavailable'):
        executor.start(job('second'), lambda event: None)


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
