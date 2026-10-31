from dataclasses import replace

import pytest

from clipflow.application.errors import JobRuleError
from clipflow.application.submission import SubmissionService
from clipflow.domain.models import DownloadOptions, JobState, Service
from tests.helpers import MemoryJobRepository


@pytest.fixture
def system(tmp_path):
    store = MemoryJobRepository()
    presets = {service: DownloadOptions(folder=tmp_path / service.value) for service in Service}
    return SubmissionService(store), store, presets


def test_mixed_batch_ignores_bad_lines_and_preserves_per_service_snapshot(system):
    service, store, presets = system
    presets[Service.YOUTUBE] = replace(presets[Service.YOUTUBE], format='mkv')
    preview = service.preview(
        '\n'.join(
            [
                'https://instagram.com/p/ABC/',
                'https://instagram.com/author/',
                'https://music.youtube.com/watch?v=track',
                'not a link',
                'https://www.instagram.com/p/ABC/?img_index=2',
            ]
        ),
        presets,
    )
    assert len(preview.requests) == 3
    assert [issue.line for issue in preview.invalid] == [4]
    assert preview.duplicate_lines == (5,)
    presets[Service.YOUTUBE] = replace(presets[Service.YOUTUBE], format='mp3')
    result = service.submit(preview)
    assert len(result.added) == 3
    assert store.get(result.added[2]).request.options.format == 'mp3'
    assert store.get(result.added[0]).request.options.folder.name == 'instagram'
    assert store.get(result.added[1]).request.profile_limit == 10


def test_single_mode_rejects_profile(system):
    service, _store, presets = system
    preview = service.preview('https://instagram.com/author/', presets, mode='single')
    assert not preview.requests
    assert len(preview.invalid) == 1
    assert not service.submit(preview).added


@pytest.mark.parametrize('limit', [10, 50, None])
def test_profile_limit_is_explicit(system, limit):
    service, _store, presets = system
    presets[Service.INSTAGRAM] = replace(presets[Service.INSTAGRAM], post_folder=False)
    preview = service.preview(
        'https://instagram.com/author/', presets, mode='profile', profile_limit=limit
    )
    assert len(preview.requests) == 1
    assert preview.requests[0].profile_limit == limit
    assert preview.requests[0].options.post_folder
    assert not presets[Service.INSTAGRAM].post_folder


def test_quality_probe_cannot_block_submission(system):
    service, store, presets = system
    # There is no GUI/quality_pending input: creating a job never waits for network metadata.
    preview = service.preview('https://instagram.com/p/ABC/', presets, mode='single')
    result = service.submit(preview)
    assert store.get(result.added[0]).state == JobState.QUEUED


def test_completed_job_requires_explicit_repeat(system):
    service, store, presets = system
    preview = service.preview('https://youtu.be/abc', presets)
    first = service.submit(preview).added[0]
    store.update(replace(store.get(first), state=JobState.COMPLETED))
    result = service.submit(preview)
    assert result.added == ()
    assert result.existing == (first,)
    repeated = service.repeat(first)
    assert repeated != first
    assert store.get(repeated).state == JobState.QUEUED
    assert store.get(repeated).request == store.get(first).request
    with pytest.raises(JobRuleError) as raised:
        service.repeat(repeated)
    assert raised.value.code == 'job_not_repeatable'


def test_repeated_submission_points_to_active_job(system):
    service, store, presets = system
    preview = service.preview('https://youtu.be/abc', presets)
    first = service.submit(preview).added[0]
    store.update(replace(store.get(first), state=JobState.COMPLETED))
    active = service.repeat(first)
    assert service.submit(preview).existing == (active,)
    assert len(store.list()) == 2


def test_playlist_mode_resolves_watch_url_list_without_changing_single(system):
    service, _store, presets = system
    url = 'https://youtube.com/watch?v=abc&list=PL_test'
    single = service.preview(url, presets, mode='single').requests[0]
    playlist = service.preview(url, presets, mode='playlist').requests[0]
    assert single.link.canonical_id == 'abc'
    assert playlist.link.canonical_id == 'PL_test'
    assert playlist.link.canonical_url == 'https://www.youtube.com/playlist?list=PL_test'


def test_invalid_url_error_redacts_credentials(system):
    service, _store, presets = system
    preview = service.preview('https://user:secret-password@instagram.com/p/abc/', presets)
    assert len(preview.invalid) == 1
    assert 'secret-password' not in repr(preview)


def test_playlist_id_cannot_be_truncated_into_another_playlist(system):
    service, _store, presets = system
    preview = service.preview(
        'https://youtube.com/watch?v=abc&list=PL%26other=evil', presets, mode='playlist'
    )
    assert not preview.requests
    assert len(preview.invalid) == 1


def test_unsupported_mode_raises_invalid_mode(system):
    service, _store, presets = system
    with pytest.raises(JobRuleError) as raised:
        service.preview('https://youtu.be/abc', presets, 'nonsense')
    assert raised.value.code == 'invalid_mode'
