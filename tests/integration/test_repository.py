import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timezone
from pathlib import Path

import pytest

from clipflow.domain.models import DownloadOptions, DownloadRequest, Job, JobState, PlaylistPosition
from clipflow.domain.urls import parse_url
from clipflow.infrastructure.repository import RepositoryError, SqliteJobRepository


def job(folder, identity='one', state=JobState.QUEUED):
    return Job(
        identity, DownloadRequest(parse_url('https://youtu.be/ABC'), DownloadOptions(folder)), state
    )


def test_music_playlist_title_persists_and_old_position_still_loads(tmp_path):
    original = Job(
        'music',
        DownloadRequest(
            parse_url('https://music.youtube.com/watch?v=track'),
            DownloadOptions(tmp_path),
            playlist=PlaylistPosition('PL_music', 2, 'Sound City'),
        ),
    )
    path = tmp_path / 'music.sqlite3'
    repo = SqliteJobRepository(path)
    repo.add(original)
    repo.close()
    repo = SqliteJobRepository(path)
    try:
        saved = repo.get('music')
        assert saved.request.link.is_music and saved.request.options.format == 'mp3'
        assert saved.request.playlist.title == 'Sound City' and saved.request.playlist.index == 2
    finally:
        repo.close()
    import json

    with sqlite3.connect(path) as db:
        payload = json.loads(db.execute('SELECT payload FROM jobs').fetchone()[0])
        payload['request']['playlist'].pop('title')
        db.execute('UPDATE jobs SET payload=?', (json.dumps(payload),))
    repo = SqliteJobRepository(path)
    try:
        old = repo.get('music').request
        assert (
            old.playlist.title is None and old.playlist.index == 2 and old.options.format == 'mp3'
        )
    finally:
        repo.close()


@pytest.mark.parametrize(
    'state', [JobState.QUEUED, JobState.PROBING, JobState.DOWNLOADING, JobState.PROCESSING]
)
def test_restart_recovers_active_as_paused(tmp_path, state):
    path = tmp_path / 'queue.sqlite3'
    repo = SqliteJobRepository(path)
    original = replace(
        job(tmp_path, state=state),
        attempt_id='old-attempt',
        automatic_retry=True,
        next_allowed_at=datetime(2099, 1, 1, tzinfo=UTC),
    )
    repo.add(original)
    repo.close()
    repo = SqliteJobRepository(path)
    try:
        recovered = repo.recover()[0]
        assert recovered.state == JobState.PAUSED and recovered.pause_reason == 'restart'
        assert recovered.attempt_id is None and not recovered.automatic_retry
        assert recovered.next_allowed_at == original.next_allowed_at
        assert repo.recover() == (recovered,)
    finally:
        repo.close()


def test_completed_history_preserved(tmp_path):
    path = tmp_path / 'queue.sqlite3'
    media = tmp_path / 'done.mp4'
    media.write_bytes(b'owned-file')
    original = replace(job(tmp_path, state=JobState.COMPLETED), result_files=(media,))
    repo = SqliteJobRepository(path)
    repo.add(original)
    repo.close()
    repo = SqliteJobRepository(path)
    try:
        repo.recover()
        assert repo.history() == (original,)
        repo.clear_history()
        assert repo.history() == () and media.read_bytes() == b'owned-file'
    finally:
        repo.close()


def test_snapshots_playlist_selection_parent_and_order_roundtrip(tmp_path):
    repo = SqliteJobRepository(tmp_path / 'queue.sqlite3')
    parent = job(tmp_path, 'parent', JobState.COMPLETED)
    request = replace(
        parent.request,
        playlist=PlaylistPosition('PLabc', 7),
        selection=('item1', 'item2'),
        options=replace(
            parent.request.options, format='webm', max_height=720, auth_profile='yt-main'
        ),
    )
    child = replace(job(tmp_path, 'child'), request=request, parent_id='parent')
    repo.add(parent)
    repo.add(child)
    assert repo.get('child') == child and repo.list() == (parent, child)
    repo.update(replace(child, state=JobState.PAUSED, pause_reason='user'))
    repo.clear_history()  # Keep an ancestor needed by a live child.
    assert [j.id for j in repo.list()] == ['parent', 'child']
    with pytest.raises(ValueError):
        repo.add(child)
    with pytest.raises(KeyError):
        repo.update(replace(child, id='missing'))
    with pytest.raises(KeyError):
        repo.get('missing')
    repo.close()
    repo.close()


def test_unknown_schema_never_overwrites(tmp_path):
    path = tmp_path / 'queue.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('PRAGMA user_version=99')
        db.execute('CREATE TABLE future (value TEXT)')
        db.execute("INSERT INTO future VALUES ('preserve')")
    before = path.read_bytes()
    with pytest.raises(RepositoryError, match='unsupported_queue_schema'):
        SqliteJobRepository(path)
    assert path.read_bytes() == before


def test_busy_db_reports_failure(tmp_path):
    path = tmp_path / 'queue.sqlite3'
    repo = SqliteJobRepository(path)
    with sqlite3.connect(path) as held:
        held.execute('BEGIN IMMEDIATE')
        with pytest.raises(RepositoryError, match='storage_busy'):
            repo.add(job(tmp_path))
    assert repo.list() == ()
    repo.close()


def test_corrupt_database_is_preserved_and_reported(tmp_path):
    path = tmp_path / 'queue.sqlite3'
    path.write_bytes(b'corrupt database - preserve original')
    before = path.read_bytes()
    with pytest.raises(RepositoryError, match='queue_corrupt'):
        SqliteJobRepository(path)
    assert path.read_bytes() == before


def test_readonly_data_directory_reports_actionable_error(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError('attempt to write a readonly database')

    monkeypatch.setattr(sqlite3, 'connect', fail)
    with pytest.raises(RepositoryError, match='storage_read_only'):
        SqliteJobRepository(tmp_path / 'queue.sqlite3')


def test_no_credentials_or_signed_cdn_urls_persisted(tmp_path):
    path = tmp_path / 'queue.sqlite3'
    repo = SqliteJobRepository(path)
    url = 'https://player02.getcourse.ru/sign-player?json=SIGNED_SECRET&signature=TOKEN_SECRET'
    original = replace(
        job(tmp_path),
        request=DownloadRequest(
            parse_url(url), DownloadOptions(tmp_path, auth_profile='school-main')
        ),
        error='https://cdn.invalid/video?token=ERROR_SECRET',
    )
    repo.add(original)
    assert repo.get('one').request == original.request  # Current run can still execute it.
    repo.close()
    assert all(
        secret not in path.read_bytes()
        for secret in [b'SIGNED_SECRET', b'TOKEN_SECRET', b'ERROR_SECRET']
    )
    repo = SqliteJobRepository(path)
    try:
        recovered = repo.recover()[0]
        assert recovered.state == JobState.PAUSED and recovered.pause_reason == 'source_required'
        assert recovered.source_required
        assert recovered.request.options.auth_profile == 'school-main'
        assert 'SIGNED_SECRET' not in repr(recovered)
        from clipflow.application.scheduler import Scheduler
        from tests.support.scheduler import ControlledExecutor

        worker = ControlledExecutor()
        scheduler = Scheduler(repo, worker)
        scheduler.start()
        assert worker.runs == []
        with pytest.raises(ValueError, match='source'):
            scheduler.resume('one')
        scheduler.provide_source('one', parse_url(url))
        scheduler.resume('one')
        assert worker.runs[0][0].request.link == original.request.link
    finally:
        repo.close()


def test_cooldown_and_manual_pause_survive_recovery_without_auto_retry(tmp_path):
    path = tmp_path / 'queue.sqlite3'
    repo = SqliteJobRepository(path)
    original = replace(
        job(tmp_path, state=JobState.PAUSED),
        pause_reason='rate_limit',
        automatic_retry=True,
        next_allowed_at=datetime(2099, 1, 1, tzinfo=UTC),
    )
    repo.add(original)
    repo.close()
    repo = SqliteJobRepository(path)
    try:
        restored = repo.recover()[0]
        assert restored.pause_reason == 'rate_limit' and not restored.automatic_retry
        assert restored.next_allowed_at == original.next_allowed_at
    finally:
        repo.close()


def test_secret_source_cannot_run_before_recover_or_be_replaced_by_another_video(tmp_path):
    from clipflow.application.scheduler import Scheduler
    from tests.support.scheduler import ControlledExecutor

    path = tmp_path / 'queue.sqlite3'
    repo = SqliteJobRepository(path)
    link = parse_url('https://player02.getcourse.ru/sign-player?json=ORIGINAL_SECRET')
    original = replace(job(tmp_path), request=DownloadRequest(link, DownloadOptions(tmp_path)))
    repo.add(original)
    repo.close()
    repo = SqliteJobRepository(path)
    worker = ControlledExecutor()
    scheduler = Scheduler(repo, worker)
    try:
        scheduler.start()
        assert worker.runs == []
        repo.recover()
        with pytest.raises(ValueError, match='Source changed'):
            scheduler.provide_source(
                'one', parse_url('https://player02.getcourse.ru/sign-player?json=OTHER_VIDEO')
            )
        scheduler.provide_source('one', link)
        scheduler.resume('one')
        assert worker.runs[0][0].request.link == link
    finally:
        repo.close()


def test_failed_update_rolls_back_previous_snapshot(tmp_path):
    path = tmp_path / 'queue.sqlite3'
    repo = SqliteJobRepository(path)
    original = job(tmp_path)
    repo.add(original)
    with sqlite3.connect(path) as held:
        held.execute('BEGIN IMMEDIATE')
        with pytest.raises(RepositoryError, match='storage_busy'):
            repo.update(replace(original, state=JobState.COMPLETED))
    assert repo.get('one') == original
    repo.close()


def test_corrupt_payload_identity_is_not_accepted(tmp_path):
    import json

    path = tmp_path / 'queue.sqlite3'
    repo = SqliteJobRepository(path)
    repo.add(job(tmp_path))
    repo.close()
    with sqlite3.connect(path) as db:
        raw = json.loads(db.execute('SELECT payload FROM jobs').fetchone()[0])
        raw['id'] = 'other'
        db.execute('UPDATE jobs SET payload=?', (json.dumps(raw),))
    before = path.read_bytes()
    with pytest.raises(RepositoryError, match='queue_corrupt'):
        SqliteJobRepository(path)
    assert path.read_bytes() == before


def test_invalid_flags_or_nonlocal_result_never_commit(tmp_path):
    repo = SqliteJobRepository(tmp_path / 'queue.sqlite3')
    with pytest.raises(ValueError):
        repo.add(replace(job(tmp_path), automatic_retry='yes'))
    with pytest.raises(ValueError):
        repo.add(
            replace(job(tmp_path), result_files=(Path('https://cdn.invalid/?token=RESULT_SECRET'),))
        )
    assert repo.list() == ()
    repo.close()


def test_secret_source_dedup_survives_restart(tmp_path):
    from clipflow.application.submission import SubmissionService
    from clipflow.domain.models import Service

    path = tmp_path / 'queue.sqlite3'
    repo = SqliteJobRepository(path)
    url = 'https://player02.getcourse.ru/sign-player?json=DEDUP_SECRET'
    options = DownloadOptions(tmp_path)
    repo.add(replace(job(tmp_path), request=DownloadRequest(parse_url(url), options)))
    repo.close()
    repo = SqliteJobRepository(path)
    repo.recover()
    try:
        submission = SubmissionService(repo)
        preview = submission.preview(url, {service: options for service in Service})
        result = submission.submit(preview)
        assert result.added == () and result.existing == ('one',) and len(repo.list()) == 1
    finally:
        repo.close()


@pytest.mark.parametrize(
    'state,reason,command',
    [(JobState.COMPLETED, None, 'retry'), (JobState.PAUSED, 'selection_required', 'select_items')],
)
def test_source_required_blocks_other_start_commands(tmp_path, state, reason, command):
    from clipflow.application.scheduler import Scheduler
    from tests.support.scheduler import ControlledExecutor

    path = tmp_path / 'queue.sqlite3'
    repo = SqliteJobRepository(path)
    link = parse_url('https://player02.getcourse.ru/sign-player?json=SECRET')
    repo.add(
        replace(
            job(tmp_path, state=state),
            request=DownloadRequest(link, DownloadOptions(tmp_path)),
            pause_reason=reason,
        )
    )
    repo.close()
    repo = SqliteJobRepository(path)
    repo.recover()
    worker = ControlledExecutor()
    scheduler = Scheduler(repo, worker)
    try:
        with pytest.raises(ValueError, match='source'):
            getattr(scheduler, command)(
                'one', ('id',)
            ) if command == 'select_items' else scheduler.retry('one')
        with pytest.raises(ValueError):
            scheduler.provide_source('one', parse_url('https://youtu.be/ABC'))
        assert worker.runs == []
    finally:
        repo.close()


def test_file_saved_before_commit_is_reconciled_on_explicit_resume(tmp_path):
    import base64

    from clipflow.application.scheduler import Scheduler
    from clipflow.domain.events import CancellationToken, JobEvent, WorkFinished
    from clipflow.providers.base import ExecutionContext, MediaItem
    from clipflow.providers.media import MediaPipeline
    from tests.instagram_fixtures import Auth, Gate

    # Real PNG with no network. A previously published file survives the DB gap.
    path = tmp_path / 'queue.sqlite3'
    repo = SqliteJobRepository(path)
    request = DownloadRequest(parse_url('https://instagram.com/p/ABC/'), DownloadOptions(tmp_path))
    original = replace(job(tmp_path, state=JobState.DOWNLOADING), request=request)
    repo.add(original)
    item = MediaItem(
        '1',
        1,
        'photo',
        'Photo',
        {
            'url': 'http://127.0.0.1:1/must-not-fetch.png',
            'ext': 'png',
            'author': 'alice',
            'post_code': 'ABC',
            'post_title': 'Photo',
        },
    )
    from clipflow.domain.paths import PostIdentity, output_path

    target = output_path(request, item, 'alice', PostIdentity('ABC', 'Photo', None))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(
        base64.b64decode(
            'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Zl1sAAAAASUVORK5CYII='
        )
    )
    before = target.stat().st_mtime_ns
    repo.close()  # Simulated loss after atomic media publish, before FilesSaved/commit.
    repo = SqliteJobRepository(path)
    repo.recover()

    class Executor:
        def start(self, job, emit):
            def send(event):
                emit(JobEvent(job.id, job.attempt_id, event))

            MediaPipeline().save(
                item, job.request, ExecutionContext(CancellationToken(), send, Auth(), Gate())
            )
            send(WorkFinished())

        def stop(self, *args):
            pass

    scheduler = Scheduler(repo, Executor())
    scheduler.start()
    assert repo.get('one').state == JobState.PAUSED
    scheduler.resume('one')
    assert repo.get('one').state == JobState.COMPLETED
    assert repo.get('one').result_files == (target,) and target.stat().st_mtime_ns == before
    repo.close()


def test_display_title_and_label_persist_and_old_records_load(tmp_path):
    import json

    request = DownloadRequest(
        parse_url('https://music.youtube.com/watch?v=track'),
        DownloadOptions(tmp_path),
        label='Мелом',
    )
    path = tmp_path / 'titles.sqlite3'
    repo = SqliteJobRepository(path)
    repo.add(Job('titled', request, title='Пропаганда - Мелом'))
    repo.close()
    repo = SqliteJobRepository(path)
    try:
        saved = repo.get('titled')
        assert saved.title == 'Пропаганда - Мелом' and saved.request.label == 'Мелом'
    finally:
        repo.close()
    with sqlite3.connect(path) as db:
        payload = json.loads(db.execute('SELECT payload FROM jobs').fetchone()[0])
        payload.pop('title')
        payload['request'].pop('label')
        db.execute('UPDATE jobs SET payload=?', (json.dumps(payload),))
    repo = SqliteJobRepository(path)
    try:
        old = repo.get('titled')
        assert old.title is None and old.request.label is None
    finally:
        repo.close()
