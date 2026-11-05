"""An Instagram rate policy over a temporary store."""

from datetime import UTC, datetime, timedelta

from clipflow.application.instagram_rate_policy import InstagramRatePolicy
from clipflow.domain.events import CancellationToken
from clipflow.infrastructure.rate_limit_store import RateLimitStore


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 28, tzinfo=UTC)
        self.waits = []

    def __call__(self):
        return self.now

    def wait(self, token, seconds):
        token.raise_if_cancelled()
        self.waits.append(seconds)
        self.now += timedelta(seconds=seconds)
        return False


def policy(tmp_path):
    clock = Clock()
    gate = InstagramRatePolicy(
        RateLimitStore(tmp_path / 'instagram-rate.sqlite3'),
        clock=clock,
        random=lambda: 0,
        wait=clock.wait,
    )
    return gate, clock, CancellationToken()
