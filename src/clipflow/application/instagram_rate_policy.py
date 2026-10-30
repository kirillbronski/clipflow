"""One cancellable budget for profile pages, probes and media in all clients."""

from contextlib import contextmanager
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import random as randomness
import time
from uuid import uuid4

from clipflow.domain.events import RateLimitDeferred, WorkCancelled

RateLimitDecision = RateLimitDeferred


class InstagramDeferred(WorkCancelled):
    def __init__(self, decision):
        super().__init__('pause')
        self.decision = decision


class InstagramRatePolicy:
    def __init__(
        self, store, *, clock=None, random=None, wait=None, diagnostic=None, monotonic=None
    ):
        self.store = store
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.random = random or randomness.random
        self.wait = wait or (lambda token, seconds: token.wait(seconds))
        self.diagnostic = diagnostic or (lambda record: None)
        self.monotonic = monotonic or time.monotonic

    def _decision(self, state):
        return RateLimitDecision(state.next_allowed_at, state.strikes < 3, 'rate_limit')

    def acquire(self, kind, cancel):
        if kind not in {'metadata', 'post', 'page', 'cdn'}:
            raise ValueError('Unknown request category')
        cancel.raise_if_cancelled()
        state = self.store.load()
        if state.next_allowed_at > self.clock():
            raise InstagramDeferred(self._decision(state))
        gap = 0 if kind == 'cdn' else 3 if kind == 'metadata' else 10 + 10 * self.random()
        slot = self.store.reserve(kind, self.clock(), gap)
        seconds = max(0, (slot - self.clock()).total_seconds())
        if seconds > 60:
            raise InstagramDeferred(RateLimitDecision(slot, True, 'rate_spacing'))
        if seconds:
            self.wait(cancel, seconds)
        cancel.raise_if_cancelled()
        # A different instance may have received a 429 while this one waited.
        state = self.store.load()
        if state.next_allowed_at > self.clock():
            raise InstagramDeferred(self._decision(state))
        self.diagnostic(
            {
                'category': kind,
                'time': self.clock().isoformat(),
                'status': 'allowed',
                'delay': seconds,
                'retry': state.strikes,
            }
        )

    def record_429(self, retry_after):
        now = self.clock()
        delay = 0
        try:
            if retry_after and retry_after.isascii() and retry_after.strip().isdigit():
                delay = int(retry_after)
            elif retry_after:
                delay = max(0, (parsedate_to_datetime(retry_after) - now).total_seconds())
        except (ValueError, TypeError, OverflowError):
            pass
        state = self.store.reject(now, delay, max(0, self.random()) * 3)
        self.diagnostic(
            {
                'category': 'instagram',
                'time': now.isoformat(),
                'status': 429,
                'delay': (state.next_allowed_at - now).total_seconds(),
                'retry': state.strikes,
            }
        )
        return self._decision(state)

    def defer_until(self, deadline):
        self.store.save_cooldown(deadline, self.store.load().strikes)

    def library_wait(self, seconds, cancel):
        from datetime import timedelta

        self.defer_until(self.clock() + timedelta(seconds=max(0, seconds)))
        if seconds > 60:
            raise InstagramDeferred(self._decision(self.store.load()))
        if seconds > 0:
            self.wait(cancel, seconds)
        cancel.raise_if_cancelled()

    def record_completed_post(self):
        self.store.complete(self.clock())

    @contextmanager
    def request(self, kind, cancel):
        from threading import Event, Thread

        owner = uuid4().hex
        started = self.monotonic()
        while not self.store.claim(owner, self.clock()):
            cancel.raise_if_cancelled()
            if self.monotonic() - started > 60:
                from datetime import timedelta

                deadline = max(self.clock(), self.store.load().last_seen) + timedelta(seconds=90)
                raise InstagramDeferred(RateLimitDecision(deadline, True, 'rate_spacing'))
            self.wait(cancel, 0.25)
        stopped = Event()
        lost = Event()

        def heartbeat():
            while not stopped.wait(20):
                try:
                    if not self.store.claim(owner, self.clock()):
                        lost.set()
                        return
                except Exception:
                    lost.set()
                    return

        def check():
            cancel.raise_if_cancelled()
            if lost.is_set():
                raise WorkCancelled('pause')

        thread = Thread(target=heartbeat, daemon=True, name='instagram-lease')
        try:
            self.acquire(kind, cancel)
            thread.start()
            yield check
        finally:
            stopped.set()
            if thread.is_alive():
                thread.join(11)
            self.store.release(owner)


@contextmanager
def gated_request(context, kind):
    """Emit once at the outer transport boundary; workers then acknowledge teardown."""
    try:
        with context.instagram_rate.request(kind, context.cancel) as renew:
            yield renew
    except InstagramDeferred as error:
        context.emit(error.decision)
        raise
