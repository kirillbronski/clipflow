"""One speed limit shared by every running download: a token bucket refilled once a second."""

import threading
import time

from clipflow.domain.events import CancellationToken

_SLICE = 0.1  # a pause or a lifted limit is noticed within this many seconds


class RateLimiter:
    def __init__(self, clock=time.monotonic, sleep=time.sleep):
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._rate: int | None = None
        self._tokens = 0.0
        self._stamp = clock()

    @property
    def rate(self) -> int | None:
        return self._rate

    def set_rate(self, bytes_per_second: int | None) -> None:
        with self._lock:
            self._refill()
            self._rate = bytes_per_second
            if bytes_per_second is None:
                self._tokens = 0.0
            else:
                # A new limit carries at most one second of debt or of saved allowance.
                self._tokens = max(-bytes_per_second, min(self._tokens, bytes_per_second))

    def consume(self, count: int, cancel: CancellationToken) -> None:
        with self._lock:
            if self._rate is None:
                return
            self._refill()
            self._tokens -= count
        while True:
            cancel.raise_if_cancelled()
            with self._lock:
                if self._rate is None:
                    return
                self._refill()
                if self._tokens > -1:  # less than a byte owed: float rounding, not debt
                    return
                wait = min(_SLICE, -self._tokens / self._rate)
            self._sleep(wait)

    def _refill(self) -> None:
        now = self._clock()
        if self._rate is not None:
            self._tokens = min(self._rate, self._tokens + (now - self._stamp) * self._rate)
        self._stamp = now
