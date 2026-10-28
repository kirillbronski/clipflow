from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import pytest

from clipflow.application.instagram_rate_policy import InstagramRatePolicy, InstagramDeferred
from clipflow.infrastructure.rate_limit_store import RateLimitStore
from clipflow.domain.events import CancellationToken, WorkCancelled


class Clock:
    def __init__(self): self.now = datetime(2026, 10, 28, tzinfo=timezone.utc); self.waits = []
    def __call__(self): return self.now
    def wait(self, token, seconds):
        token.raise_if_cancelled()
        self.waits.append(seconds)
        self.now += timedelta(seconds=seconds)
        return False


def policy(tmp_path):
    clock = Clock()
    gate = InstagramRatePolicy(RateLimitStore(tmp_path/'instagram-rate.sqlite3'), clock=clock,
                               random=lambda: 0, wait=clock.wait)
    return gate, clock, CancellationToken()


def test_metadata_minimum_3_seconds(tmp_path):
    gate, clock, token = policy(tmp_path)
    gate.acquire('metadata', token); gate.acquire('metadata', token)
    assert clock.waits == [3]


def test_shared_budget_across_instaloader_ytdlp_probe(tmp_path):
    gate, clock, token = policy(tmp_path)
    other = InstagramRatePolicy(RateLimitStore(gate.store.path), clock=clock, random=lambda:0, wait=clock.wait)
    gate.acquire('metadata', token); other.acquire('metadata', token); gate.acquire('metadata', token)
    assert clock.waits == [3, 3]


def test_page_post_gap_10_to_20(tmp_path):
    gate, clock, token = policy(tmp_path)
    gate.acquire('page', token); gate.acquire('post', token)
    assert 10 <= sum(clock.waits) <= 20


@pytest.mark.parametrize('header', ['2000', 'date'])
def test_retry_after_seconds_and_http_date(tmp_path, header):
    gate, clock, token = policy(tmp_path)
    deadline = clock.now + timedelta(seconds=2000)
    decision = gate.record_429(format_datetime(deadline, usegmt=True) if header=='date' else header)
    assert decision.next_allowed_at == deadline
    with pytest.raises(InstagramDeferred): gate.acquire('metadata',token)


def test_invalid_retry_after_falls_back(tmp_path):
    gate, clock, _ = policy(tmp_path)
    assert (gate.record_429('invalid').next_allowed_at-clock.now).total_seconds() == 900


def test_library_wait_wins(tmp_path):
    gate, clock, token = policy(tmp_path)
    deadline = clock.now + timedelta(seconds=5000)
    with pytest.raises(InstagramDeferred): gate.library_wait(5000,token)
    assert gate.record_429('10').next_allowed_at == deadline


def test_short_library_wait_cancellable_and_not_added_to_spacing(tmp_path):
    gate,clock,token=policy(tmp_path)
    gate.acquire('page',token)
    gate.library_wait(15,token); gate.acquire('page',token)
    assert clock.waits==[15]


def test_user_pause_disables_automatic_retry_and_other_instagram_jobs_wait(tmp_path):
    from clipflow.application.scheduler import Scheduler
    from clipflow.domain.events import RateLimitDeferred, WorkStopped
    from clipflow.domain.models import Job, JobState
    from tests.helpers import MemoryJobRepository
    from tests.unit.test_scheduler import ControlledExecutor, request as youtube_request
    from tests.instagram_fixtures import request
    repo=MemoryJobRepository(); worker=ControlledExecutor(); clock=Clock()
    repo.add(Job('ig1',request(tmp_path))); repo.add(Job('ig2',request(tmp_path,'https://instagram.com/p/DEF/')))
    repo.add(Job('yt',youtube_request()))
    scheduler=Scheduler(repo,worker,clock=clock); scheduler.start()
    worker.emit(RateLimitDeferred(clock.now+timedelta(seconds=900),True)); worker.emit(WorkStopped())
    assert worker.runs[-1][0].id=='yt'
    assert repo.get('ig2').state==JobState.PAUSED
    scheduler.pause('ig1')
    clock.now+=timedelta(seconds=900); scheduler.tick()
    assert repo.get('ig1').state==JobState.PAUSED and not repo.get('ig1').automatic_retry
    assert repo.get('ig2').state==JobState.QUEUED


def test_429_backoff_900_1800_3600_then_manual(tmp_path):
    gate, clock, _ = policy(tmp_path)
    for seconds, automatic in [(900,True),(1800,True),(3600,False),(3600,False)]:
        decision = gate.record_429(None)
        assert (decision.next_allowed_at-clock.now).total_seconds() == seconds
        assert decision.automatic_retry is automatic
        clock.now = decision.next_allowed_at


def test_cooldown_survives_restart_and_clock_rollback(tmp_path):
    gate, clock, token = policy(tmp_path)
    gate.acquire('metadata', token)
    decision = gate.record_429(None)
    clock.now -= timedelta(days=1)
    other = InstagramRatePolicy(RateLimitStore(gate.store.path), clock=clock, wait=clock.wait)
    with pytest.raises(InstagramDeferred) as error: other.acquire('metadata',token)
    assert error.value.decision.next_allowed_at == decision.next_allowed_at
    assert other.store.load().strikes == 1


def test_cancel_interrupts_wait(tmp_path):
    gate, clock, token = policy(tmp_path)
    gate.acquire('metadata', token)
    def cancel_wait(token, seconds): token.cancel('cancel'); token.raise_if_cancelled()
    gate.wait = cancel_wait
    with pytest.raises(WorkCancelled): gate.acquire('metadata',token)


def test_real_cancel_wakes_cross_process_lease_wait(tmp_path):
    from threading import Timer
    from time import monotonic
    store=RateLimitStore(tmp_path/'rate.sqlite3')
    assert store.claim('other-process',datetime.now(timezone.utc))
    gate=InstagramRatePolicy(store); token=CancellationToken()
    timer=Timer(.03,lambda:token.cancel('cancel')); timer.start(); started=monotonic()
    try:
        with pytest.raises(WorkCancelled):
            with gate.request('metadata',token): pytest.fail('Acquired a busy lease')
        assert monotonic()-started<1
    finally: timer.cancel(); timer.join()


def test_cdn_not_throttled_per_chunk(tmp_path):
    gate, clock, token = policy(tmp_path)
    gate.acquire('cdn',token); gate.acquire('cdn',token)
    assert clock.waits == []


def test_instagram_cooldown_releases_youtube_worker():
    from clipflow.application.scheduler import Scheduler
    from clipflow.domain.events import RateLimitDeferred, WorkStopped
    from clipflow.domain.models import Job, JobState
    from tests.helpers import MemoryJobRepository
    from tests.unit.test_scheduler import ControlledExecutor, request
    repo = MemoryJobRepository(); worker = ControlledExecutor(); clock = Clock()
    repo.add(Job('ig',request('one'))); repo.add(Job('yt',request('two')))
    scheduler = Scheduler(repo,worker,clock=clock); scheduler.start()
    worker.emit(RateLimitDeferred(clock.now+timedelta(seconds=900),True))
    assert len(worker.runs)==1
    worker.emit(WorkStopped())
    assert worker.runs[-1][0].id=='yt' and repo.get('ig').state==JobState.PAUSED
    clock.now += timedelta(seconds=900); scheduler.tick()
    assert repo.get('ig').state==JobState.QUEUED


def test_manual_cooldown_does_not_auto_resume():
    from clipflow.application.scheduler import Scheduler
    from clipflow.domain.events import RateLimitDeferred, WorkStopped
    from clipflow.domain.models import Job, JobState
    from tests.helpers import MemoryJobRepository
    from tests.unit.test_scheduler import ControlledExecutor, request
    repo=MemoryJobRepository(); worker=ControlledExecutor(); clock=Clock()
    repo.add(Job('ig',request()))
    scheduler=Scheduler(repo,worker,clock=clock); scheduler.start()
    worker.emit(RateLimitDeferred(clock.now,False)); worker.emit(WorkStopped()); scheduler.tick()
    assert repo.get('ig').state==JobState.PAUSED
