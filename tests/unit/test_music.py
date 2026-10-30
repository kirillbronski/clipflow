import hashlib
from dataclasses import replace

import pytest

from clipflow.application.submission import SubmissionService
from clipflow.domain.events import RequestsDiscovered
from clipflow.domain.models import DownloadOptions, DownloadRequest, PlaylistPosition, Service
from clipflow.domain.paths import output_path
from clipflow.domain.urls import InvalidLink, parse_url, request_key
from clipflow.providers.media import MediaPipeline
from clipflow.providers.youtube import YouTubeProvider
from tests.helpers import MemoryJobRepository
from tests.unit.test_youtube_provider import context, extract_fixture, playlist


@pytest.mark.parametrize('route', ['watch?v=track', 'playlist?list=PL_music'])
def test_music_origin_forces_audio_without_mutating_preset(tmp_path, route):
    options = DownloadOptions(tmp_path, format='mkv', max_height=720)
    link = parse_url('https://music.youtube.com/' + route)
    request = DownloadRequest(link, options)
    assert link.is_music and link.canonical_url.startswith('https://music.youtube.com/')
    assert request.options.format == 'mp3' and request.options.max_height is None
    assert options.format == 'mkv' and options.max_height == 720
    assert (
        DownloadRequest(parse_url('https://youtube.com/watch?v=track'), options).options == options
    )


def test_music_playlist_mode_batch_and_identity(tmp_path):
    presets = {s: DownloadOptions(tmp_path, format='mp4') for s in Service}
    submission = SubmissionService(MemoryJobRepository())
    value = submission.preview(
        'https://music.youtube.com/watch?v=track&list=PL_music', presets, 'playlist'
    )
    assert not value.invalid and value.requests[0].link.is_music
    assert value.requests[0].options.format == 'mp3'
    batch = submission.preview(
        'https://music.youtube.com/watch?v=track\nhttps://youtube.com/watch?v=video', presets
    )
    assert [r.options.format for r in batch.requests] == ['mp3', 'mp4']
    same = DownloadRequest(
        parse_url('https://youtube.com/watch?v=track'), DownloadOptions(tmp_path, format='mp3')
    )
    assert request_key(batch.requests[0]) == request_key(same)
    for fake in [
        'https://music.youtube.com.evil.test/watch?v=track',
        'https://user@music.youtube.com/watch?v=track',
    ]:
        with pytest.raises(InvalidLink):
            parse_url(fake)


def test_playlist_title_survives_children_and_is_not_identity(tmp_path, monkeypatch):
    info = playlist()
    info['title'] = 'Sound City'
    extract_fixture(monkeypatch, info)
    request = DownloadRequest(
        parse_url('https://music.youtube.com/playlist?list=PL_music'), DownloadOptions(tmp_path)
    )
    provider = YouTubeProvider(MediaPipeline())
    ctx, events = context()
    assert provider.probe(request, ctx).collection_title == 'Sound City'
    provider.execute(request, ctx)
    children = [
        child
        for event in events
        if isinstance(event, RequestsDiscovered)
        for child in event.requests
    ]
    assert children and all(
        child.link.is_music and child.options.format == 'mp3' for child in children
    )
    child = children[0]
    assert child.playlist.title == 'Sound City'
    renamed = replace(child, playlist=replace(child.playlist, title='Renamed'))
    assert request_key(child) == request_key(renamed)
    from clipflow.providers.base import MediaItem

    media = MediaItem('video_A', 1, 'video', 'Track', {})
    target = output_path(child, media, None, None)
    assert target.parent.name == 'Sound City [PL_music]' and target.name == 'Track.mp3'
    other = replace(child, playlist=replace(child.playlist, playlist_id='PL_other'))
    assert target.parent != output_path(other, media, None, None).parent
    fallback = replace(child, playlist=PlaylistPosition('PL_music', 1))
    assert output_path(fallback, media, None, None).parent.name.startswith('PL_music')
    unsafe = replace(child, playlist=replace(child.playlist, title='../CON:/bad'))
    assert output_path(unsafe, media, None, None).resolve().is_relative_to(tmp_path.resolve())


def test_mp3_320_does_not_reuse_old_192_path(tmp_path):
    from clipflow.providers.base import MediaItem

    request = DownloadRequest(
        parse_url('https://youtube.com/watch?v=track'), DownloadOptions(tmp_path, format='mp3')
    )
    target = output_path(request, MediaItem('track', 1, 'video', 'Song', {}), None, None)
    old_digest = hashlib.sha256(b'track\0None').hexdigest()[:16]
    assert old_digest not in target.name
