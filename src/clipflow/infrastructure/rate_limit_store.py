"""Independent cross-process Instagram budget. No URLs, sessions or credentials."""

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


def stamp(value):
    if value.tzinfo is None:
        raise ValueError('UTC-aware time required')
    return value.timestamp()


def utc(value):
    return datetime.fromtimestamp(value, UTC)


@dataclass(frozen=True)
class RateLimitState:
    next_allowed_at: datetime
    strikes: int
    last_seen: datetime


class RateLimitStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1):
                raise ValueError('Unsupported Instagram rate schema')
            db.execute(
                'CREATE TABLE IF NOT EXISTS budget (id INTEGER PRIMARY KEY CHECK(id=1), last_seen REAL NOT NULL, slot REAL NOT NULL, gap REAL NOT NULL, deadline REAL NOT NULL, strikes INTEGER NOT NULL, owner TEXT, lease REAL NOT NULL)'
            )
            db.execute('INSERT OR IGNORE INTO budget VALUES (1,0,0,0,0,0,NULL,0)')
            db.execute(
                'CREATE TABLE IF NOT EXISTS checkpoints (key TEXT PRIMARY KEY, cursor TEXT, codes TEXT NOT NULL, complete INTEGER NOT NULL)'
            )
            db.execute(
                'CREATE TABLE IF NOT EXISTS completed (profile TEXT NOT NULL, code TEXT NOT NULL, PRIMARY KEY(profile,code))'
            )
            db.execute('PRAGMA user_version=1')

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def reserve(self, kind, now_utc, minimum_gap):
        if minimum_gap < 0:
            raise ValueError('Negative interval')
        with self._db() as db:
            seen, slot, gap, deadline = db.execute(
                'SELECT last_seen,slot,gap,deadline FROM budget'
            ).fetchone()
            now = max(stamp(now_utc), seen)
            # CDN is serialized by the lease; no deliberate media-chunk pacing.
            spacing = max(gap, minimum_gap) if kind != 'cdn' else 0
            selected = max(now, deadline, slot + spacing)
            db.execute('UPDATE budget SET last_seen=?,slot=?,gap=?', (now, selected, minimum_gap))
            return utc(selected)

    def load(self):
        with self._db() as db:
            deadline, strikes, seen = db.execute(
                'SELECT deadline,strikes,last_seen FROM budget'
            ).fetchone()
            return RateLimitState(utc(deadline), strikes, utc(seen))

    def save_cooldown(self, deadline, strikes):
        with self._db() as db:
            db.execute(
                'UPDATE budget SET deadline=MAX(deadline,?),strikes=MAX(strikes,?)',
                (stamp(deadline), strikes),
            )

    def reject(self, now_utc, delay, jitter):
        """Atomically increment strikes so two processes cannot reset backoff."""
        with self._db() as db:
            seen, deadline, strikes = db.execute(
                'SELECT last_seen,deadline,strikes FROM budget'
            ).fetchone()
            now = max(stamp(now_utc), seen)
            strikes += 1
            deadline = max(
                deadline, now + max(delay, (900, 1800, 3600)[min(strikes - 1, 2)]) + jitter
            )
            db.execute(
                'UPDATE budget SET deadline=?,strikes=?,last_seen=?', (deadline, strikes, now)
            )
            return RateLimitState(utc(deadline), strikes, utc(now))

    def complete(self, now_utc):
        with self._db() as db:
            db.execute('UPDATE budget SET strikes=0 WHERE deadline<=?', (stamp(now_utc),))

    def claim(self, owner, now_utc):
        with self._db() as db:
            seen, held, until = db.execute('SELECT last_seen,owner,lease FROM budget').fetchone()
            now = max(stamp(now_utc), seen)
            if held not in (None, owner) and until > now:
                return False
            db.execute('UPDATE budget SET owner=?,lease=?,last_seen=?', (owner, now + 90, now))
            return True

    def release(self, owner):
        with self._db() as db:
            db.execute('UPDATE budget SET owner=NULL,lease=0 WHERE owner=?', (owner,))

    def checkpoint(self, key, cursor, codes, complete):
        # Only bounded opaque cursors/ASCII IDs. Never store a request URL.
        import re

        if cursor is not None and (
            len(cursor) > 512 or not re.fullmatch(r'[A-Za-z0-9_:.=-]+', cursor)
        ):
            cursor = None
        codes = tuple(dict.fromkeys(codes))
        if not all(re.fullmatch(r'[A-Za-z0-9_-]{1,100}', v) for v in codes):
            raise ValueError('Invalid post code')
        with self._db() as db:
            db.execute(
                'INSERT OR REPLACE INTO checkpoints VALUES (?,?,?,?)',
                (key, cursor, json.dumps(codes), bool(complete)),
            )

    def get_checkpoint(self, key):
        with self._db() as db:
            row = db.execute(
                'SELECT cursor,codes,complete FROM checkpoints WHERE key=?', (key,)
            ).fetchone()
            return (row[0], tuple(json.loads(row[1])), bool(row[2])) if row else None

    def mark_completed(self, profile, code):
        import re

        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', code):
            raise ValueError('Invalid code')
        with self._db() as db:
            db.execute('INSERT OR IGNORE INTO completed VALUES (?,?)', (profile, code))

    def completed_ids(self, profile):
        with self._db() as db:
            return frozenset(
                r[0] for r in db.execute('SELECT code FROM completed WHERE profile=?', (profile,))
            )
