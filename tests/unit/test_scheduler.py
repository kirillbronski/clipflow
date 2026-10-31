"""Queue behavior with controllable workers: no GUI, network, or wall-clock sleeps."""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from clipflow.application.errors import RULE_CODES, JobRuleError
from clipflow.application.scheduler import Scheduler
from clipflow.domain.events import (
    CancellationToken,
    FilesSaved,
    JobEvent,
    ProgressChanged,
    RateLimitDeferred,
    RequestsDiscovered,
    SelectionRequired,
    StageChanged,
    WorkCancelled,
    WorkFailed,
    WorkFinished,
    WorkStopped,
)
from clipflow.domain.models import DownloadOptions, DownloadRequest, Job, JobState
from clipflow.domain.urls import parse_url
from tests.helpers import MemoryJobRepository
from tests.support.scheduler import ControlledExecutor, request


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
    assert repo.get('three').state == JobState.QUEUED
    assert len(worker.runs) == 2
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
    with pytest.raises(JobRuleError) as raised:
        scheduler.retry('one')
    assert raised.value.code == 'job_not_retryable'
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
    with pytest.raises(JobRuleError) as raised:
        scheduler.resume('one')
    assert raised.value.code == 'job_not_resumable'
    with pytest.raises(JobRuleError) as raised:
        scheduler.select_items('one', ())
    assert raised.value.code == 'selection_not_expected'
    scheduler.select_items('one', ('b',))
    assert original.selection is None
    assert repo.get('one').request.selection == ('b',)
    assert len(worker.runs) == 1
    worker.emit(WorkStopped())
    assert repo.get('one').state == JobState.PROBING
    assert repo.get('one').attempt_id != old_attempt


def test_rate_limit_pauses_and_keeps_deadline_without_claiming_success(queue):
    repo, worker, scheduler = queue
    deadline = datetime(2099, 1, 1, tzinfo=UTC)
    scheduler.start()
    worker.emit(RateLimitDeferred(deadline, automatic_retry=False))
    assert repo.get('one').state == JobState.PAUSED
    assert repo.get('one').pause_reason == 'rate_limit'
    assert repo.get('one').next_allowed_at == deadline
    with pytest.raises(JobRuleError) as raised:
        scheduler.resume('one')
    assert raised.value.code == 'cooldown_active'
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
    repo, _worker, scheduler = queue
    scheduler.handle(JobEvent('missing', 'missing', WorkFailed('ignored')))
    with pytest.raises(JobRuleError) as raised:
        scheduler.resume('one')
    assert raised.value.code == 'job_not_resumable'
    with pytest.raises(JobRuleError) as raised:
        scheduler.select_items('one', ('a',))
    assert raised.value.code == 'selection_not_expected'
    scheduler.pause('two')
    scheduler.start()
    assert repo.get('two').state == JobState.PAUSED
    scheduler.cancel('two', include_children=False)
    scheduler.pause('two')
    assert repo.get('two').state == JobState.CANCELLED


def test_subscription_reports_progress_and_can_unsubscribe(queue):
    _repo, worker, scheduler = queue
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
    repo, _worker, _ = queue

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
    with pytest.raises(ValueError, match='Invalid cancellation reason'):
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
    with pytest.raises(OSError, match='stop unavailable'):
        scheduler.pause('one')
    scheduler.resume('one')
    assert repo.get('two').state == JobState.QUEUED
    assert len(worker.runs) == 1
    worker.emit(WorkStopped())
    assert len(worker.runs) == 2


def test_cancel_without_children_leaves_child_queued(queue):
    repo, _worker, scheduler = queue
    repo.add(Job('child', request('child'), parent_id='one'))
    scheduler.cancel('one', include_children=False)
    scheduler.start()
    assert repo.get('child').state == JobState.QUEUED
    assert repo.get('two').state == JobState.PROBING


def test_shutdown_is_final_even_with_no_active_worker(queue):
    _repo, worker, scheduler = queue
    scheduler.shutdown()
    scheduler.shutdown()
    with pytest.raises(JobRuleError) as raised:
        scheduler.start()
    assert raised.value.code == 'scheduler_closed'
    assert worker.runs == []


def test_unexpected_worker_stop_pauses_instead_of_completing(queue):
    repo, worker, scheduler = queue
    scheduler.start()
    worker.emit(WorkStopped())
    assert repo.get('one').state == JobState.PAUSED
    assert repo.get('two').state == JobState.PROBING


def test_unsubscribe_is_idempotent_and_unknown_payload_is_ignored(queue):
    _repo, worker, scheduler = queue
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


def _set(repo, identity, **changes):
    repo.update(replace(repo.get(identity), **changes))


FUTURE = datetime(2099, 1, 1, tzinfo=UTC)
RULE_CASES = [
    ('scheduler_closed', lambda r, s: s.shutdown(), lambda s: s.start()),
    (
        'job_not_startable',
        lambda r, s: _set(r, 'one', state=JobState.PAUSED),
        lambda s: s.start('one'),
    ),
    (
        'source_required',
        lambda r, s: _set(r, 'one', state=JobState.PAUSED, source_required=True),
        lambda s: s.resume('one'),
    ),
    (
        'source_required',
        lambda r, s: _set(r, 'one', state=JobState.FAILED, source_required=True),
        lambda s: s.retry('one'),
    ),
    (
        'source_required',
        lambda r, s: _set(r, 'one', state=JobState.PAUSED, source_required=True),
        lambda s: s.select_items('one', ('a',)),
    ),
    ('job_not_resumable', lambda r, s: None, lambda s: s.resume('one')),
    (
        'cooldown_active',
        lambda r, s: _set(r, 'one', state=JobState.PAUSED, next_allowed_at=FUTURE),
        lambda s: s.resume('one'),
    ),
    ('job_not_retryable', lambda r, s: None, lambda s: s.retry('one')),
    (
        'source_not_expected',
        lambda r, s: None,
        lambda s: s.provide_source('one', parse_url('https://youtu.be/first')),
    ),
    (
        'source_changed',
        lambda r, s: _set(r, 'one', state=JobState.FAILED, source_required=True),
        lambda s: s.provide_source('one', parse_url('https://youtu.be/other')),
    ),
    ('selection_not_expected', lambda r, s: None, lambda s: s.select_items('one', ('a',))),
    ('selection_not_expected', lambda r, s: None, lambda s: s.refresh_selection('one')),
]


@pytest.mark.parametrize(('code', 'arrange', 'act'), RULE_CASES)
def test_rule_errors_carry_codes(queue, code, arrange, act):
    repo, _worker, scheduler = queue
    arrange(repo, scheduler)
    with pytest.raises(JobRuleError) as raised:
        act(scheduler)
    assert raised.value.code == code
    assert isinstance(raised.value, ValueError)  # callers that catch ValueError keep working
    assert code in RULE_CODES


def test_rule_codes_without_own_text_keep_the_generic_message():
    from clipflow.ui.i18n import CATALOG

    shown = {code for code in RULE_CODES if 'error.' + code in CATALOG['ru']}
    assert shown == {'source_changed', 'cooldown_active'}


class CountingRepository(MemoryJobRepository):
    """Counts full reads: each one decodes the whole queue in the real SQLite store."""

    def __init__(self):
        super().__init__()
        self.reads = 0

    def list(self):
        self.reads += 1
        return super().list()


def test_stop_all_reads_a_long_queue_once():
    repo = CountingRepository()
    playlist = DownloadRequest(
        parse_url('https://music.youtube.com/playlist?list=PL_x'), DownloadOptions(Path('/d'))
    )
    repo.add(Job('parent', playlist, state=JobState.COMPLETED))
    for n in range(700):
        repo.add(Job(f'c{n:03d}', request(f'v{n:04d}'), parent_id='parent'))
    worker = ControlledExecutor()
    scheduler = Scheduler(repo, worker)
    scheduler.start()
    repo.reads = 0
    cancelled = scheduler.clear_queue()
    assert len(cancelled) == 700
    assert all(repo.get(f'c{n:03d}').state == JobState.CANCELLED for n in range(700))
    assert worker.stops == [('c000', 'cancel')]
    assert repo.reads <= 2  # was two full reads per job: 700 tracks took minutes


def test_cancel_one_job_still_cancels_its_children():
    repo = MemoryJobRepository()
    repo.add(Job('p', request('p0')))
    repo.add(Job('c', request('c0'), parent_id='p'))
    repo.add(Job('g', request('g0'), parent_id='c'))
    repo.add(Job('other', request('o0')))
    scheduler = Scheduler(repo, ControlledExecutor())
    scheduler.cancel('p')
    assert [repo.get(i).state for i in ('p', 'c', 'g', 'other')] == [
        JobState.CANCELLED,
        JobState.CANCELLED,
        JobState.CANCELLED,
        JobState.QUEUED,
    ]


def long_playlist(size=700, state=JobState.QUEUED):
    repo = CountingRepository()
    playlist = DownloadRequest(
        parse_url('https://www.youtube.com/playlist?list=PL_group'), DownloadOptions(Path('/d'))
    )
    repo.add(Job('parent', playlist, state=JobState.COMPLETED))
    for n in range(size):
        repo.add(Job(f'c{n:03d}', request(f'v{n:04d}'), state=state, parent_id='parent'))
    return repo, [f'c{n:03d}' for n in range(size)]


def test_group_pause_reads_a_long_queue_once():
    repo, ids = long_playlist()
    scheduler = Scheduler(repo, ControlledExecutor())
    repo.reads = 0
    assert scheduler.pause_many(ids) == tuple(ids)
    assert all(repo.get(i).state == JobState.PAUSED for i in ids)
    assert {repo.get(i).pause_reason for i in ids} == {'user'}
    assert repo.reads <= 2


def test_group_pause_stops_the_active_job():
    repo, ids = long_playlist(3)
    worker = ControlledExecutor()
    scheduler = Scheduler(repo, worker)
    scheduler.start()
    assert worker.runs[-1][0].id == 'c000'
    scheduler.pause_many(ids)
    assert worker.stops == [('c000', 'pause')]


def test_group_resume_skips_jobs_that_cannot_resume():
    repo = MemoryJobRepository()
    future = datetime(2999, 1, 1, tzinfo=UTC)
    repo.add(Job('user', request('u'), state=JobState.PAUSED, pause_reason='user'))
    repo.add(Job('pick', request('p'), state=JobState.PAUSED, pause_reason='selection_required'))
    repo.add(
        Job('src', request('s'), state=JobState.PAUSED, pause_reason='user', source_required=True)
    )
    repo.add(
        Job(
            'wait',
            request('w'),
            state=JobState.PAUSED,
            pause_reason='rate_limit',
            next_allowed_at=future,
        )
    )
    scheduler = Scheduler(repo, ControlledExecutor())
    assert scheduler.resume_many(('user', 'pick', 'src', 'wait')) == ('user',)
    assert repo.get('user').state == JobState.QUEUED
    assert [repo.get(i).state for i in ('pick', 'src', 'wait')] == [JobState.PAUSED] * 3


def test_group_retry_requeues_failed_and_cancelled_only():
    repo, ids = long_playlist(state=JobState.FAILED)
    repo.update(replace(repo.get('c001'), state=JobState.CANCELLED))
    repo.update(replace(repo.get('c002'), state=JobState.COMPLETED))
    repo.update(replace(repo.get('c003'), source_required=True))
    scheduler = Scheduler(repo, ControlledExecutor())
    repo.reads = 0
    retried = scheduler.retry_many(ids)
    assert 'c001' in retried
    assert 'c002' not in retried
    assert 'c003' not in retried
    assert repo.get('c000').state == JobState.QUEUED
    assert repo.get('c000').error is None
    assert repo.get('c002').state == JobState.COMPLETED
    assert repo.get('c003').state == JobState.FAILED
    assert repo.reads <= 2


def test_group_pause_takes_over_an_automatic_wait_and_skips_finished_jobs():
    repo = MemoryJobRepository()
    repo.add(Job('auto', request('a'), state=JobState.PAUSED, automatic_retry=True))
    repo.add(Job('mine', request('m'), state=JobState.PAUSED, pause_reason='user'))
    repo.add(Job('done', request('d'), state=JobState.COMPLETED))
    scheduler = Scheduler(repo, ControlledExecutor())
    assert scheduler.pause_many(('auto', 'mine', 'done')) == ('auto',)
    assert repo.get('auto').pause_reason == 'user'
    assert not repo.get('auto').automatic_retry
    assert scheduler.resume_many(('done',)) == ()
    assert scheduler.retry_many(('mine',)) == ()
