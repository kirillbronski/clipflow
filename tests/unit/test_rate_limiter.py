"""One speed limit shared by every running download."""

import threading
import time

import pytest

from clipflow.domain.events import CancellationToken, WorkCancelled
from clipflow.infrastructure.rate_limiter import RateLimiter

MIB = 1024 * 1024


class Clock:
    """Model time: sleeping moves the clock, nothing really waits."""

    def __init__(self):
        self.now = 100.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def limiter(rate=None):
    clock = Clock()
    result = RateLimiter(clock=clock, sleep=clock.sleep)
    result.set_rate(rate)
    return result, clock


def test_no_limit_never_sleeps():
    limit, clock = limiter()
    for _ in range(100):
        limit.consume(10 * MIB, CancellationToken())
    assert clock.sleeps == []
    assert limit.rate is None


def test_total_of_two_threads_matches_rate():
    limit, clock = limiter(MIB)
    start = clock.now
    consumed = 0
    tokens = (CancellationToken(), CancellationToken())
    turn = 0
    while clock.now - start < 5:
        limit.consume(65536, tokens[turn % 2])
        consumed += 65536
        turn += 1
    assert 4 * MIB <= consumed <= 6 * MIB
    assert all(seconds <= 0.1 + 1e-9 for seconds in clock.sleeps)


def test_rate_change_applies_at_once():
    limit, clock = limiter(MIB)
    cancel = CancellationToken()
    limit.consume(MIB, cancel)
    limit.consume(MIB, cancel)  # waits about a second at 1 MiB/s
    limit.set_rate(10 * MIB)
    before = clock.now
    limit.consume(MIB, cancel)
    assert clock.now - before <= 0.2 + 1e-9


def test_cancel_interrupts_wait():
    clock = Clock()
    cancel = CancellationToken()

    def sleep(seconds):
        clock.sleep(seconds)
        cancel.cancel('pause')

    limit = RateLimiter(clock=clock, sleep=sleep)
    limit.set_rate(MIB)
    with pytest.raises(WorkCancelled):
        limit.consume(10 * MIB, cancel)
    assert len(clock.sleeps) == 1


def test_removing_limit_wakes_sleeper():
    limit = RateLimiter()
    limit.set_rate(1024)
    done = threading.Event()

    def download():
        limit.consume(100 * 1024 * 1024, CancellationToken())
        done.set()

    worker = threading.Thread(target=download, daemon=True)
    worker.start()
    time.sleep(0.05)
    assert not done.is_set()
    removed = time.monotonic()
    limit.set_rate(None)
    assert done.wait(1)
    assert time.monotonic() - removed <= 0.2
