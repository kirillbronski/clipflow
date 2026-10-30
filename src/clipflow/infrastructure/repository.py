"""Atomic queue/history snapshots; secrets stay in memory or protected auth storage."""

import json
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from clipflow.domain.models import (
    TERMINAL_STATES,
    ContentKind,
    DownloadRequest,
    Job,
    JobState,
    ParsedLink,
    PlaylistPosition,
    Service,
)
from clipflow.domain.urls import parse_url, source_reference
from clipflow.infrastructure.serialization import decode_options, encode_options, path_value


class RepositoryError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def storage_code(error):
    code = (getattr(error, 'sqlite_errorcode', 0) or 0) & 255
    if code in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
        return 'storage_busy'
    if (
        code == sqlite3.SQLITE_READONLY
        or isinstance(error, PermissionError)
        or 'readonly' in str(error).lower()
    ):
        return 'storage_read_only'
    if code in {sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB}:
        return 'queue_corrupt'
    if code == sqlite3.SQLITE_FULL or getattr(error, 'errno', None) == 28:
        return 'storage_full'
    return 'storage_unavailable'


def _identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', value):
        raise ValueError('invalid_job_identity')
    return value


def _safe_link(link):
    """A secret-bearing source becomes a non-executable reference on disk."""
    parsed = urlparse(link.canonical_url)
    if (
        link.service == Service.GETCOURSE
        and re.fullmatch(r'protected-[0-9a-f]{64}', link.canonical_id)
        and parsed.scheme == 'https'
        and not parsed.query
        and parsed.path == '/'
        and not parsed.username
        and not parsed.password
        and re.fullmatch(r'[a-z0-9.-]+', parsed.netloc)
    ):
        return link, True
    canonical = parse_url(link.canonical_url)
    if canonical != link:
        raise ValueError('invalid_job_source')
    if link.service != Service.GETCOURSE:
        return canonical, False
    query = parse_qs(parsed.query, keep_blank_values=True)
    safe = (
        link.kind == ContentKind.LESSON
        and parsed.path == '/pl/teach/control/lesson/view'
        and set(query) <= {'id', 'editMode'}
        and len(query.get('id', [])) == 1
        and re.fullmatch(r'[0-9]{1,20}', query['id'][0])
        and (not query.get('editMode') or query['editMode'] in (['0'], ['1']))
    )
    if safe:
        return canonical, False
    identity = source_reference(link)
    return ParsedLink(link.service, link.kind, identity, f'https://{parsed.hostname}/'), True


def _safe_error(value):
    if value is None:
        return None
    if isinstance(value, str) and re.fullmatch(
        r'[a-z][a-z0-9_]{0,79}(?::[0-9]{1,3}:[a-z][a-z0-9_]{0,79})?', value
    ):
        return value
    return 'download_failed'


def _encode(job):
    if type(job.automatic_retry) is not bool or type(job.source_required) is not bool:
        raise ValueError('invalid_job_flags')
    _identifier(job.id)
    if job.parent_id is not None:
        _identifier(job.parent_id)
    if any(not path_value(str(path)).is_absolute() for path in job.result_files):
        raise ValueError('local_result_path_required')
    link, redacted = _safe_link(job.request.link)
    selection = job.request.selection
    if selection is not None:
        for value in selection:
            _identifier(value)
    if job.next_allowed_at is not None and job.next_allowed_at.tzinfo is None:
        raise ValueError('aware_deadline_required')
    raw = {
        'id': job.id,
        'state': job.state.value,
        'attempt_id': job.attempt_id,
        'parent_id': job.parent_id,
        'result_files': [str(p) for p in job.result_files],
        'error': _safe_error(job.error),
        'pause_reason': _safe_error(job.pause_reason),
        'next_allowed_at': job.next_allowed_at.isoformat() if job.next_allowed_at else None,
        'automatic_retry': job.automatic_retry,
        'source_required': redacted or job.source_required,
        'title': job.title,
        'request': {
            'link': {
                'service': link.service.value,
                'kind': link.kind.value,
                'canonical_id': link.canonical_id,
                'canonical_url': link.canonical_url,
            },
            'options': encode_options(job.request.options),
            'selection': selection,
            'profile_limit': job.request.profile_limit,
            'playlist': {
                'playlist_id': job.request.playlist.playlist_id,
                'index': job.request.playlist.index,
                'title': job.request.playlist.title,
            }
            if job.request.playlist
            else None,
            'label': job.request.label,
        },
    }
    if job.attempt_id is not None:
        _identifier(job.attempt_id)
    return json.dumps(raw, ensure_ascii=False, allow_nan=False), redacted


def _decode(text):
    raw = json.loads(text)
    data = raw.pop('request')
    link = data['link']
    if data['selection'] is not None and not isinstance(data['selection'], list):
        raise ValueError('invalid_selection')
    if not isinstance(raw['result_files'], list):
        raise ValueError('invalid_result_files')
    parsed = ParsedLink(
        Service(link['service']),
        ContentKind(link['kind']),
        link['canonical_id'],
        link['canonical_url'],
    )
    safe, redacted = _safe_link(parsed)
    if safe != parsed:
        raise ValueError('unsafe_persisted_source')
    request = DownloadRequest(
        parsed,
        decode_options(data['options']),
        tuple(data['selection']) if data['selection'] is not None else None,
        data['profile_limit'],
        PlaylistPosition(**data['playlist']) if data['playlist'] else None,
        data.get('label'),
    )  # names arrived in 2.0.4
    raw.setdefault('title', None)
    raw['state'] = JobState(raw['state'])
    raw['result_files'] = tuple(path_value(p) for p in raw['result_files'])
    raw['next_allowed_at'] = (
        datetime.fromisoformat(raw['next_allowed_at']) if raw['next_allowed_at'] else None
    )
    if type(raw['automatic_retry']) is not bool or type(raw['source_required']) is not bool:
        raise ValueError('invalid_job_flags')
    if redacted and not raw['source_required']:
        raise ValueError('invalid_source_reference')
    job = Job(request=request, **raw)
    _encode(job)  # Validate references, dates and options without retaining raw exceptions.
    return job


class SqliteJobRepository:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._connection = None
        self._volatile = {}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(self.path, timeout=0.25, isolation_level=None)
            db = self._connection
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1):
                raise RepositoryError('unsupported_queue_schema')
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if version == 0 and tables:
                raise RepositoryError('unsupported_queue_schema')
            if version == 1 and tables != {'jobs'}:
                raise RepositoryError('queue_corrupt')
            db.execute('PRAGMA synchronous=FULL')
            if version == 0:
                with self._transaction() as db:
                    db.execute('CREATE TABLE jobs (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
                    db.execute('PRAGMA user_version=1')
            if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise RepositoryError('queue_corrupt')
            self.list()  # Validate existing payloads before any recovery writes.
        except (sqlite3.Error, OSError) as error:
            self.close()
            raise RepositoryError(storage_code(error)) from None
        except BaseException:
            self.close()
            raise

    def _db(self):
        if self._connection is None:
            raise RepositoryError('storage_closed')
        return self._connection

    @contextmanager
    def _transaction(self):
        db = self._db()
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.execute('COMMIT')
        except (sqlite3.Error, OSError) as error:
            if db.in_transaction:
                db.execute('ROLLBACK')
            raise RepositoryError(storage_code(error)) from None
        except BaseException:
            if db.in_transaction:
                db.execute('ROLLBACK')
            raise

    def _rows(self, where='', params=()):
        try:
            return (
                self._db()
                .execute('SELECT id,payload FROM jobs ' + where + ' ORDER BY rowid', params)
                .fetchall()
            )
        except sqlite3.Error as error:
            raise RepositoryError(storage_code(error)) from None

    def _restore(self, identity, payload, volatile=True):
        try:
            job = _decode(payload)
            if job.id != identity:
                raise ValueError('invalid_job_identity')
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
            raise RepositoryError('queue_corrupt') from None
        if volatile and job.id in self._volatile:
            job = replace(job, request=self._volatile[job.id], source_required=False)
        return job

    def _remember(self, job, redacted):
        self._volatile.pop(job.id, None)
        if redacted and not job.source_required:
            self._volatile[job.id] = job.request

    def add(self, job):
        payload, redacted = _encode(job)
        with self._transaction() as db:
            if db.execute('SELECT 1 FROM jobs WHERE id=?', (job.id,)).fetchone():
                raise ValueError('Duplicate job ID')
            db.execute('INSERT INTO jobs VALUES (?,?)', (job.id, payload))
        self._remember(job, redacted)

    def update(self, job):
        payload, redacted = _encode(job)
        with self._transaction() as db:
            if db.execute('UPDATE jobs SET payload=? WHERE id=?', (payload, job.id)).rowcount != 1:
                raise KeyError(job.id)
        self._remember(job, redacted)

    def get(self, job_id):
        rows = self._rows('WHERE id=?', (job_id,))
        if not rows:
            raise KeyError(job_id)
        return self._restore(*rows[0])

    def list(self):
        return tuple(self._restore(*row) for row in self._rows())

    def history(self):
        return tuple(job for job in self.list() if job.state in TERMINAL_STATES)

    def recover(self):
        with self._transaction() as db:
            jobs = tuple(self._restore(*row, volatile=False) for row in self._rows())
            recovered = []
            for job in jobs:
                if job.state not in TERMINAL_STATES:
                    reason = (
                        'source_required'
                        if job.source_required
                        else 'restart'
                        if job.state != JobState.PAUSED
                        else job.pause_reason
                    )
                    job = replace(
                        job,
                        state=JobState.PAUSED,
                        pause_reason=reason,
                        attempt_id=None,
                        automatic_retry=False,
                    )
                    db.execute('UPDATE jobs SET payload=? WHERE id=?', (_encode(job)[0], job.id))
                recovered.append(job)
        self._volatile.clear()
        return tuple(recovered)

    def clear_history(self):
        with self._transaction() as db:
            jobs = self.list()
            protected = {j.id for j in jobs if j.state not in TERMINAL_STATES}
            while True:
                expanded = protected | {
                    j.parent_id for j in jobs if j.id in protected and j.parent_id is not None
                }
                if expanded == protected:
                    break
                protected = expanded
            removed = {j.id for j in jobs if j.state in TERMINAL_STATES and j.id not in protected}
            db.executemany('DELETE FROM jobs WHERE id=?', ((identity,) for identity in removed))
        for identity in removed:
            self._volatile.pop(identity, None)

    def remove(self, identities):
        identities = set(identities)
        with self._transaction() as db:
            jobs = self.list()
            if identities - {j.id for j in jobs}:
                raise KeyError('unknown_job')
            if any(j.parent_id in identities and j.id not in identities for j in jobs):
                raise ValueError('Parent still has children')
            db.executemany('DELETE FROM jobs WHERE id=?', ((identity,) for identity in identities))
        for identity in identities:
            self._volatile.pop(identity, None)

    def close(self):
        if self._connection is not None:
            self._connection.close()
            self._connection = None
        self._volatile.clear()
