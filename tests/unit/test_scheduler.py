"""Queue behavior with controllable workers: no GUI, network, or wall-clock sleeps."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from clipflow.application.scheduler import Scheduler
from clipflow.domain.events import (
    CancellationToken,
    WorkCancelled,
    JobEvent,
    StageChanged,
    ProgressChanged,
    FilesSaved,
    RequestsDiscovered,
    SelectionRequired,
    RateLimitDeferred,
    WorkFinished,
    WorkFailed,
    WorkStopped,
)
from clipflow.domain.models import DownloadOptions, DownloadRequest, Job, JobState
from clipflow.domain.urls import parse_url
from tests.helpers import MemoryJobRepository


class ControlledExecutor:
    """External worker boundary; termination can deliberately arrive late."""

    def __init__(self):
        self.runs = []
        self.stops = []

    def start(self, job, on_event):
        self.runs.append((job, on_event))

    def stop(self, job_id, reason):
        self.stops.append((job_id, reason))

    def emit(self, payload, run=-1):
        job, callback = self.runs[run]
        callback(JobEvent(job.id, job.attempt_id, payload))


def request(name='first'):
    return DownloadRequest(
        parse_url(f'https://youtu.be/{name}'), DownloadOptions(Path('/downloads'))
    )


@pytest.fixture
def queue():
    repo = MemoryJobRepository()
    repo.add(Job('one', request()))
    repo.add(Job('two', request('second')))
    worker = ControlledExecutor()
    return repo, worker, Scheduler(repo, worker)


def finish(worker, name='01.mp4'):
    worker.emit(FilesSaved((Path(name),)))
    worker.emit(WorkFinished())


def test_one_running_job(queue):
    repo, worker, scheduler = queue
    assert all(j.state == JobState.QUEUED for j in repo.list())
    assert worker.runs == []  # Constructing scheduler must never start network.
    scheduler.start()
    scheduler.start()
    assert [j.state for j in repo.list()] == [JobState.PROBING, JobState.QUEUED]
    finish(worker)
    assert [j.state for j in repo.list()] == [JobState.COMPLETED, JobState.PROBING]
    assert len(worker.runs) == 2


def test_drained_queue_requires_explicit_start_for_new_jobs(queue):
    repo, worker, scheduler = queue
    scheduler.start()
    finish(worker)
    finish(worker)
    repo.add(Job('three', request('third')))
    scheduler.tick()
    assert repo.get('three').state == JobState.QUEUED and len(worker.runs) == 2
    scheduler.start()
    assert worker.runs[-1][0].id == 'three'


def test_old_attempt_cannot_fail_new_attempt(queue):
    repo, worker, scheduler = queue
    scheduler.start()
    scheduler.pause('one')
    scheduler.resume('one')
    worker.emit(WorkStopped())
    new_attempt = repo.get('one').attempt_id
    worker.emit(WorkFailed('late error'), run=0)
    worker.emit(StageChanged(JobState.PROCESSING), run=0)
    worker.emit(FilesSaved((Path('old.mp4'),)), run=0)
    assert repo.get('one').state == JobState.PROBING
    assert repo.get('one').attempt_id == new_attempt
    assert repo.get('one').result_files == ()


def test_download_100_is_not_completed_before_processing(queue):
    repo, worker, scheduler = queue
    scheduler.start()
    worker.emit(StageChanged(JobState.DOWNLOADING))
    worker.emit(ProgressChanged(100, 100))
    assert repo.get('one').state == JobState.DOWNLOADING
    worker.emit(StageChanged(JobState.PROCESSING))
    worker.emit(StageChanged(JobState.DOWNLOADING))  # Late/regressive stage.
    worker.emit(StageChanged(JobState.COMPLETED))  # Only WorkFinished can finish.
    assert repo.get('one').state == JobState.PROCESSING
    finish(worker)
    assert repo.get('one').state == JobState.COMPLETED


def test_pause_preserves_partial_then_resumes_new_attempt(queue, tmp_path):
    repo, worker, scheduler = queue
    partial = tmp_path / '01.mp4.part'
    partial.write_bytes(b'partial media')
    scheduler.start()
    first = repo.get('one').attempt_id
    scheduler.pause('one')
    scheduler.resume('one')
    assert len(worker.runs) == 1  # Wait for actual stop acknowledgement.
    worker.emit(WorkStopped())
    assert repo.get('one').state == JobState.PROBING
    assert repo.get('one').attempt_id != first
    assert worker.stops == [('one', 'pause')]
    assert partial.read_bytes() == b'partial media'
    assert repo.get('two').state == JobState.QUEUED


def test_profile_cancel_cancels_unstarted_children(queue):
    repo, worker, scheduler = queue
    repo.add(Job('child', request('child'), parent_id='one'))
    repo.add(
        Job(
            'done',
            request('done'),
            state=JobState.COMPLETED,
            parent_id='one',
            result_files=(Path('saved.mp4'),),
        )
    )
    repo.add(Job('grandchild', request('grandchild'), parent_id='child'))
    scheduler.start()
    scheduler.cancel('one')
    assert repo.get('child').state == repo.get('grandchild').state == JobState.CANCELLED
    assert repo.get('done').result_files == (Path('saved.mp4'),)
    assert repo.get('done').state == JobState.COMPLETED
    assert repo.get('two').state == JobState.QUEUED
    worker.emit(WorkStopped())
    assert repo.get('two').state == JobState.PROBING


def test_failure_advances_queue(queue):
    repo, worker, scheduler = queue
    scheduler.start()
    worker.emit(WorkFailed('network unavailable'))
    assert repo.get('one').state == JobState.FAILED
    assert repo.get('one').error == 'network unavailable'
    assert repo.get('two').state == JobState.PROBING


def test_shutdown_does_not_start_next(queue):
    repo, worker, scheduler = queue
    scheduler.start()
    scheduler.shutdown()
    worker.emit(WorkFailed('stopping'))
    assert [j.state for j in repo.list()] == [JobState.PAUSED, JobState.QUEUED]
    assert len(worker.runs) == 1
    assert worker.stops == [('one', 'shutdown')]


def test_retry_requires_terminal_and_ignores_its_old_success(queue):
    repo, worker, scheduler = queue
    scheduler.start()
    with pytest.raises(ValueError):
        scheduler.retry('one')
    worker.emit(WorkFailed('failure'))
    scheduler.retry('one')
    finish(worker)  # Complete second job; start retry.
    assert repo.get('one').state == JobState.PROBING
    assert repo.get('one').error is None
    worker.emit(WorkFinished(), run=0)
    assert repo.get('one').state == JobState.PROBING


def test_discovery_deduplicates_children_and_late_discovery_is_ignored(queue):
    repo, worker, scheduler = queue
    scheduler.start()
    worker.emit(RequestsDiscovered((request('child'), request('child'), request('second'))))
    worker.emit(RequestsDiscovered((request('child'),)))
    children = [j for j in repo.list() if j.parent_id == 'one']
    assert len(children) == 1
    assert children[0].request.link.canonical_id == 'child'
    worker.emit(WorkFinished())
    assert repo.get('one').state == JobState.COMPLETED
    worker.emit(RequestsDiscovered((request('late'),)), run=0)
    assert len(repo.list()) == 3


def test_selection_pauses_until_worker_stops_and_creates_new_snapshot(queue):
    repo, worker, scheduler = queue
    original = repo.get('one').request
    scheduler.start()
    old_attempt = repo.get('one').attempt_id
    worker.emit(SelectionRequired(('a', 'b')))
    assert repo.get('one').pause_reason == 'selection_required'
    with pytest.raises(ValueError):
        scheduler.resume('one')
    with pytest.raises(ValueError):
        scheduler.select_items('one', ())
    scheduler.select_items('one', ('b',))
    assert original.selection is None
    assert repo.get('one').request.selection == ('b',)
    assert len(worker.runs) == 1
    worker.emit(WorkStopped())
    assert repo.get('one').state == JobState.PROBING
    assert repo.get('one').attempt_id != old_attempt


def test_rate_limit_pauses_and_keeps_deadline_without_claiming_success(queue):
    repo, worker, scheduler = queue
    deadline = datetime(2099, 1, 1, tzinfo=timezone.utc)
    scheduler.start()
    worker.emit(RateLimitDeferred(deadline, automatic_retry=False))
    assert repo.get('one').state == JobState.PAUSED
    assert repo.get('one').pause_reason == 'rate_limit'
    assert repo.get('one').next_allowed_at == deadline
    with pytest.raises(ValueError):
        scheduler.resume('one')
    worker.emit(WorkStopped())
    assert repo.get('two').state == JobState.PROBING


def test_empty_success_fails_and_duplicate_saved_files_are_not_lost(queue):
    repo, worker, scheduler = queue
    scheduler.start()
    worker.emit(WorkFinished())
    assert repo.get('one').state == JobState.FAILED
    worker.emit(FilesSaved((Path('01.mp4'),)))
    worker.emit(FilesSaved((Path('01.mp4'), Path('01.txt'))))
    worker.emit(WorkFinished())
    assert repo.get('two').result_files == (Path('01.mp4'), Path('01.txt'))
    assert repo.get('two').state == JobState.COMPLETED


def test_unknown_events_and_invalid_commands_do_not_corrupt_queue(queue):
    repo, worker, scheduler = queue
    scheduler.handle(JobEvent('missing', 'missing', WorkFailed('ignored')))
    with pytest.raises(ValueError):
        scheduler.resume('one')
    with pytest.raises(ValueError):
        scheduler.select_items('one', ('a',))
    scheduler.pause('two')
    scheduler.start()
    assert repo.get('two').state == JobState.PAUSED
    scheduler.cancel('two', include_children=False)
    scheduler.pause('two')
    assert repo.get('two').state == JobState.CANCELLED


def test_subscription_reports_progress_and_can_unsubscribe(queue):
    repo, worker, scheduler = queue
    seen = []
    unsubscribe = scheduler.subscribe(seen.append)
    scheduler.start()
    worker.emit(ProgressChanged(25, 100))
    assert isinstance(seen[-1].payload, ProgressChanged)
    assert seen[-1].job_id == 'one'
    unsubscribe()
    count = len(seen)
    worker.emit(ProgressChanged(50, 100))
    assert len(seen) == count


def test_synchronous_worker_completion_does_not_recurse_through_queue():
    repo = MemoryJobRepository()
    for i in range(1100):
        repo.add(Job(str(i), request(str(i))))

    class ImmediateExecutor:
        def start(self, job, on_event):
            on_event(JobEvent(job.id, job.attempt_id, WorkFailed('offline')))

    scheduler = Scheduler(repo, ImmediateExecutor())
    scheduler.start()
    assert all(j.state == JobState.FAILED for j in repo.list())


def test_executor_start_failure_is_recorded_and_queue_continues(queue):
    repo, worker, _ = queue

    class BrokenExecutor:
        def start(self, job, on_event):
            raise OSError('worker unavailable')

    scheduler = Scheduler(repo, BrokenExecutor())
    scheduler.start()
    assert all(j.state == JobState.FAILED for j in repo.list())


@pytest.mark.parametrize('reason', ['pause', 'cancel', 'shutdown'])
def test_cancel_token_interrupts_wait_and_preserves_first_reason(reason):
    token = CancellationToken()
    assert not token.wait(0)
    token.raise_if_cancelled()
    token.cancel(reason)
    token.cancel('cancel')
    assert token.wait(60)  # Must return immediately, not sleep a minute.
    with pytest.raises(WorkCancelled) as caught:
        token.raise_if_cancelled()
    assert caught.value.reason == reason


def test_cancel_token_rejects_unknown_reason():
    token = CancellationToken()
    with pytest.raises(ValueError):
        token.cancel('unknown')


def test_observer_pause_before_worker_launch_cannot_start_paused_job(queue):
    repo, worker, scheduler = queue

    def pause_on_start(event):
        if event.job_id == 'one' and event.payload == StageChanged(JobState.PROBING):
            scheduler.pause('one')

    scheduler.subscribe(pause_on_start)
    scheduler.start()
    assert repo.get('one').state == JobState.PAUSED
    assert [j.id for j, _ in worker.runs] == ['two']
    assert worker.stops == []  # No worker existed to stop.


def test_stop_failure_never_frees_slot_or_starts_another_job(queue):
    repo, worker, scheduler = queue

    def cannot_stop(job_id, reason):
        raise OSError('stop unavailable')

    worker.stop = cannot_stop
    scheduler.start()
    with pytest.raises(OSError):
        scheduler.pause('one')
    scheduler.resume('one')
    assert repo.get('two').state == JobState.QUEUED
    assert len(worker.runs) == 1
    worker.emit(WorkStopped())
    assert len(worker.runs) == 2


def test_cancel_without_children_leaves_child_queued(queue):
    repo, worker, scheduler = queue
    repo.add(Job('child', request('child'), parent_id='one'))
    scheduler.cancel('one', include_children=False)
    scheduler.start()
    assert repo.get('child').state == JobState.QUEUED
    assert repo.get('two').state == JobState.PROBING


def test_shutdown_is_final_even_with_no_active_worker(queue):
    repo, worker, scheduler = queue
    scheduler.shutdown()
    scheduler.shutdown()
    with pytest.raises(ValueError):
        scheduler.start()
    assert worker.runs == []


def test_unexpected_worker_stop_pauses_instead_of_completing(queue):
    repo, worker, scheduler = queue
    scheduler.start()
    worker.emit(WorkStopped())
    assert repo.get('one').state == JobState.PAUSED
    assert repo.get('two').state == JobState.PROBING


def test_unsubscribe_is_idempotent_and_unknown_payload_is_ignored(queue):
    repo, worker, scheduler = queue
    seen = []
    unsubscribe = scheduler.subscribe(seen.append)
    scheduler.start()
    count = len(seen)
    worker.emit(object())
    assert len(seen) == count
    unsubscribe()
    unsubscribe()


def test_cancel_token_wakes_a_waiting_worker():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    token = CancellationToken()
    ready = Event()

    def wait_for_cancel():
        ready.set()
        return token.wait(60)

    with ThreadPoolExecutor(max_workers=1) as pool:
        waiting = pool.submit(wait_for_cancel)
        assert ready.wait(2)
        token.cancel('shutdown')
        assert waiting.result(timeout=2)


def test_discovery_already_in_queue_finishes_parent_without_duplicate_download(queue):
    repo, worker, scheduler = queue
    scheduler.start()
    worker.emit(RequestsDiscovered((request('second'),)))
    worker.emit(WorkFinished())
    assert repo.get('one').state == JobState.COMPLETED
    assert len(repo.list()) == 2
    assert repo.get('two').state == JobState.PROBING


@pytest.mark.parametrize('state', [JobState.CANCELLED, JobState.FAILED, JobState.COMPLETED])
def test_collection_retry_rediscovery_restores_terminal_children_without_outputs(tmp_path, state):
    from dataclasses import replace

    repo = MemoryJobRepository()
    parent = DownloadRequest(
        parse_url('https://youtube.com/playlist?list=PL_test'), DownloadOptions(tmp_path)
    )
    repo.add(Job('parent', parent, state=JobState.CANCELLED))
    child = request('child')
    repo.add(
        Job(
            'old-child',
            child,
            state=state,
            parent_id='parent',
            result_files=(tmp_path / 'deleted.mp4',) if state == JobState.COMPLETED else (),
        )
    )
    worker = ControlledExecutor()
    scheduler = Scheduler(repo, worker)
    scheduler.retry('parent')
    scheduler.start()
    worker.emit(RequestsDiscovered((child, child)))
    worker.emit(WorkFinished())
    restored = [job for job in repo.list() if job.id != 'old-child' and job.parent_id == 'parent']
    assert len(restored) == 1
    assert worker.runs[-1][0].id == restored[0].id
    assert repo.get(restored[0].id).state == JobState.PROBING


def test_rediscovery_keeps_verified_completed_output_and_active_work(tmp_path):
    repo = MemoryJobRepository()
    repo.add(Job('parent', request('parent')))
    child = request('child')
    saved = tmp_path / 'saved.mp4'
    saved.write_bytes(b'kept')
    repo.add(Job('done', child, state=JobState.COMPLETED, result_files=(saved,)))
    worker = ControlledExecutor()
    scheduler = Scheduler(repo, worker)
    scheduler.start()
    worker.emit(RequestsDiscovered((child, child)))
    assert len(repo.list()) == 2


def test_title_events_persist_and_named_queued_jobs_are_relabelled(queue):
    from clipflow.domain.events import TitleChanged

    repo, worker, scheduler = queue
    seen = []
    scheduler.subscribe(seen.append)
    scheduler.start()
    worker.emit(TitleChanged('Пропаганда - Мелом'))
    assert repo.get('one').title == 'Пропаганда - Мелом'
    scheduler.set_title('two', 'Оскар - Между Мной')
    assert repo.get('two').title == 'Оскар - Между Мной'
    assert any(e.job_id == 'two' and e.payload == TitleChanged('Оскар - Между Мной') for e in seen)
    scheduler.set_title('one', 'Другое')  # active jobs are named by their own worker
    assert repo.get('one').title == 'Пропаганда - Мелом'
