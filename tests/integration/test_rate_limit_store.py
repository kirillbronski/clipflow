from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime, timedelta

from clipflow.infrastructure.rate_limit_store import RateLimitStore


def reserve(path):
    return RateLimitStore(path).reserve('metadata', datetime(2026, 10, 28, tzinfo=UTC), 3)


def test_cross_process_reservation(tmp_path):
    path = tmp_path / 'instagram-rate.sqlite3'
    with ProcessPoolExecutor(max_workers=2) as pool:
        times = sorted(pool.map(reserve, [path] * 4))
    assert [(t - times[0]).total_seconds() for t in times] == [0, 3, 6, 9]


def test_leases_and_safe_checkpoints_survive_restart(tmp_path):
    path = tmp_path / 'instagram-rate.sqlite3'
    store = RateLimitStore(path)
    now = datetime.now(UTC)
    assert store.claim('first', now)
    assert not RateLimitStore(path).claim('second', now)
    store.release('first')
    assert store.claim('second', now)
    store.checkpoint('profile', 'page-2', ['ABC'], False)
    assert RateLimitStore(path).get_checkpoint('profile') == ('page-2', ('ABC',), False)
    store.save_cooldown(now + timedelta(hours=1), 2)
    assert RateLimitStore(path).load().strikes == 2


def test_completed_ids_and_expired_lease_survive_restart(tmp_path):
    store = RateLimitStore(tmp_path / 'rate.sqlite3')
    now = datetime.now(UTC)
    store.mark_completed('alice', 'ABc')
    store.mark_completed('alice', 'ABc')
    assert RateLimitStore(store.path).completed_ids('alice') == frozenset({'ABc'})
    assert store.claim('crashed', now)
    assert store.claim('restarted', now + timedelta(seconds=91))
    store.release('crashed')
    assert not store.claim('third', now + timedelta(seconds=92))


def test_unsupported_schema_and_unsafe_checkpoint_rejected(tmp_path):
    import sqlite3

    import pytest

    path = tmp_path / 'rate.sqlite3'
    store = RateLimitStore(path)
    store.checkpoint('alice', 'https://signed.example/?token=secret', ['ABC'], False)
    assert store.get_checkpoint('alice') == (None, ('ABC',), False)
    with pytest.raises(ValueError):
        store.checkpoint('alice', None, ['bad/code'], False)
    with sqlite3.connect(path) as db:
        db.execute('PRAGMA user_version=99')
    with pytest.raises(ValueError, match='Unsupported'):
        RateLimitStore(path)
