"""Several downloads at once: YouTube in N slots, Instagram and GetCourse one each beside it."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from clipflow.application.scheduler import Scheduler
from clipflow.domain.events import (
    FilesSaved,
    JobEvent,
    RateLimitDeferred,
    WorkFailed,
    WorkFinished,
    WorkStopped,
)
from clipflow.domain.models import Job, JobState, Service
from tests.helpers import MemoryJobRepository
from tests.support.scheduler import ControlledExecutor, request

YT, IG, GC = Service.YOUTUBE, Service.INSTAGRAM, Service.GETCOURSE
NAMES = {YT: 'yt', IG: 'ig', GC: '10'}


def make(*services, parallel=1, executor=None):
    """Jobs named yt1, ig1, 101… in queue order; GetCourse lessons need numeric ids."""
    repo = MemoryJobRepository()
    seen = {}
    for service in services:
        seen[service] = seen.get(service, 0) + 1
        name = f'{NAMES[service]}{seen[service]}'
        repo.add(Job(name, request(name, service)))
    worker = executor or ControlledExecutor()
    scheduler = Scheduler(repo, worker)
    scheduler.set_youtube_parallel(parallel)
    return repo, worker, scheduler


def started(worker):
    return [job.id for job, _ in worker.runs]


def send(worker, job_id, payload):
    run = max(i for i, (job, _) in enumerate(worker.runs) if job.id == job_id)
    worker.emit(payload, run=run)


def finish(worker, job_id):
    send(worker, job_id, FilesSaved((Path(f'{job_id}.mp4'),)))
    send(worker, job_id, WorkFinished())


QUEUE = (YT, YT, IG, YT, YT, GC, IG)


def test_lanes_fill_in_queue_order():
    _, worker, scheduler = make(*QUEUE, parallel=3)
    scheduler.start()
    assert started(worker) == ['yt1', 'yt2', 'ig1', 'yt3', '101']
    assert set(scheduler.active_ids) == {'yt1', 'yt2', 'ig1', 'yt3', '101'}


def test_finished_youtube_starts_next_youtube():
    _, worker, scheduler = make(*QUEUE, parallel=3)
    scheduler.start()
    finish(worker, 'yt2')
    assert started(worker)[-1] == 'yt4'


def test_second_instagram_waits_for_first():
    _, worker, scheduler = make(*QUEUE, parallel=3)
    scheduler.start()
    finish(worker, 'yt1')
    assert 'ig2' not in started(worker)
    finish(worker, 'ig1')
    assert started(worker)[-1] == 'ig2'


def test_lowering_limit_keeps_running_jobs():
    repo, worker, scheduler = make(*QUEUE, parallel=3)
    scheduler.start()
    scheduler.set_youtube_parallel(1)
    assert worker.stops == []
    finish(worker, 'yt1')
    finish(worker, 'yt2')
    assert 'yt4' not in started(worker)
    finish(worker, 'yt3')
    assert started(worker)[-1] == 'yt4'
    assert repo.get('yt3').state == JobState.COMPLETED


def test_raising_limit_starts_more_at_once():
    _, worker, scheduler = make(*QUEUE, parallel=1)
    scheduler.start()
    assert started(worker) == ['yt1', 'ig1', '101']
    scheduler.set_youtube_parallel(3)
    assert started(worker) == ['yt1', 'ig1', '101', 'yt2', 'yt3']


def test_preferred_job_waits_only_in_its_lane():
    _, worker, scheduler = make(YT, YT, YT, IG, IG, parallel=1)
    scheduler.start()
    assert started(worker) == ['yt1', 'ig1']
    scheduler.start('yt3')
    assert started(worker) == ['yt1', 'ig1']
    finish(worker, 'ig1')
    assert started(worker)[-1] == 'ig2'
    finish(worker, 'yt1')
    assert started(worker)[-1] == 'yt3'


def test_late_ack_frees_only_its_slot():
    repo, worker, scheduler = make(YT, YT, YT, YT, parallel=3)
    scheduler.start()
    scheduler.pause('yt1')
    assert worker.stops == [('yt1', 'pause')]
    assert 'yt4' not in started(worker)
    send(worker, 'yt2', FilesSaved((Path('yt2.mp4'),)))
    assert repo.get('yt2').result_files == (Path('yt2.mp4'),)
    send(worker, 'yt1', WorkStopped())
    assert started(worker)[-1] == 'yt4'
    assert set(scheduler.active_ids) == {'yt2', 'yt3', 'yt4'}
    assert repo.get('yt1').state == JobState.PAUSED


def test_pause_cancel_and_clear_queue_stop_each_active():
    repo, worker, scheduler = make(YT, YT, YT, YT, parallel=3)
    scheduler.start()
    scheduler.pause_many(['yt1', 'yt2'])
    scheduler.cancel('yt3')
    assert sorted(worker.stops) == [('yt1', 'pause'), ('yt2', 'pause'), ('yt3', 'cancel')]
    assert len(scheduler.active_ids) == 3  # slots stay taken until each worker confirms
    assert 'yt4' not in started(worker)
    scheduler.clear_queue()
    for name in ('yt1', 'yt2', 'yt3'):
        send(worker, name, WorkStopped())
    assert scheduler.active_ids == ()
    assert started(worker) == ['yt1', 'yt2', 'yt3']
    assert repo.get('yt4').state == JobState.CANCELLED


def test_shutdown_pauses_every_active():
    repo, worker, scheduler = make(YT, YT, YT, YT, parallel=3)
    scheduler.start()
    scheduler.shutdown()
    assert sorted(worker.stops) == [(n, 'shutdown') for n in ('yt1', 'yt2', 'yt3')]
    for name in ('yt1', 'yt2', 'yt3'):
        assert repo.get(name).pause_reason == 'shutdown'
        send(worker, name, WorkStopped())
    assert started(worker) == ['yt1', 'yt2', 'yt3']
    assert scheduler.active_ids == ()


def test_old_attempt_events_are_dropped():
    repo, worker, scheduler = make(YT, YT, parallel=2)
    scheduler.start()
    scheduler.pause('yt1')
    send(worker, 'yt1', WorkStopped())
    scheduler.resume('yt1')
    worker.emit(FilesSaved((Path('old.mp4'),)), run=0)
    assert repo.get('yt1').result_files == ()
    assert repo.get('yt1').state == JobState.PROBING


def test_probing_blocks_new_starts():
    worker = ControlledExecutor()
    worker.probing = True
    _, worker, scheduler = make(YT, YT, parallel=2, executor=worker)
    scheduler.start()
    assert started(worker) == []
    worker.probing = False
    scheduler.tick()
    assert started(worker) == ['yt1', 'yt2']


def test_immediate_executor_with_parallel_slots():
    order = []

    class ImmediateExecutor:
        def start(self, job, on_event):
            order.append(job.id)
            on_event(JobEvent(job.id, job.attempt_id, WorkFailed('offline')))

    repo, _, scheduler = make(*[YT] * 300, IG, GC, parallel=3, executor=ImmediateExecutor())
    scheduler.start()
    assert all(j.state == JobState.FAILED for j in repo.list())
    assert order == [j.id for j in repo.list()]


def test_instagram_deferral_leaves_youtube_running():
    repo, worker, scheduler = make(YT, YT, YT, IG, IG, parallel=2)
    scheduler.start()
    assert started(worker) == ['yt1', 'yt2', 'ig1']
    deadline = datetime.now(UTC) + timedelta(hours=1)
    send(worker, 'ig1', RateLimitDeferred(deadline, automatic_retry=True))
    assert ('ig1', 'pause') in worker.stops
    assert repo.get('ig2').state == JobState.PAUSED
    send(worker, 'ig1', WorkStopped())
    finish(worker, 'yt1')
    assert started(worker)[-1] == 'yt3'
    assert set(scheduler.active_ids) == {'yt2', 'yt3'}


@pytest.mark.parametrize('count', [0, 5, True, 2.0])
def test_set_youtube_parallel_rejects_out_of_range(count):
    scheduler = Scheduler(MemoryJobRepository(), ControlledExecutor())
    with pytest.raises(ValueError, match='1-4'):
        scheduler.set_youtube_parallel(count)
    assert scheduler.limits[YT] == 1


def test_progress_events_do_not_scan_the_queue():
    from clipflow.domain.events import ProgressChanged

    repo, worker, scheduler = make(YT, YT, IG, YT, YT, parallel=2)
    scheduler.start()
    scans = []
    original = repo.list
    repo.list = lambda: scans.append(1) or original()
    for _ in range(50):
        send(worker, 'yt1', ProgressChanged(10, 100, 1.0, 1.0))
    assert scans == []  # progress frees no slot: a long history must not be re-read per event
