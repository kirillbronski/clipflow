"""YouTube files are named "Artist - Title"; numbering is opt-in; old keys/settings stay readable."""

from dataclasses import asdict, replace
import hashlib
import json
import os

import pytest

from clipflow.domain.models import DownloadOptions, DownloadRequest, PlaylistPosition
from clipflow.domain.paths import output_path, media_identity
from clipflow.domain.urls import parse_url, request_key
from clipflow.infrastructure.serialization import decode_options, encode_options
from clipflow.providers.base import MediaItem


def track(identity='OaXj5OMqYtE', **info):
    return MediaItem(identity, 1, 'video', info.pop('title', 'Мелом'), info)


def music(tmp_path, **options):
    return DownloadRequest(
        parse_url('https://music.youtube.com/watch?v=OaXj5OMqYtE'),
        DownloadOptions(tmp_path, **options),
    )


def test_artist_and_track_without_hash(tmp_path):
    path = output_path(music(tmp_path), track(artists=['Пропаганда'], track='Мелом'), None, None)
    assert path == tmp_path / 'YouTube' / 'Пропаганда - Мелом.mp3'


def test_several_artists_and_single_artist_field(tmp_path):
    assert (
        output_path(music(tmp_path), track(artists=['A', 'B'], track='T'), None, None).name
        == 'A, B - T.mp3'
    )
    assert (
        output_path(music(tmp_path), track(artist='Оскар', track='Между Мной'), None, None).name
        == 'Оскар - Между Мной.mp3'
    )


def test_plain_video_keeps_its_title(tmp_path):
    req = DownloadRequest(parse_url('https://youtu.be/dQw4w9WgXcQ'), DownloadOptions(tmp_path))
    item = MediaItem(
        'dQw4w9WgXcQ',
        1,
        'video',
        'Rick Astley - Never Gonna Give You Up (Official Video)',
        {'uploader': 'Rick Astley'},
    )
    assert (
        output_path(req, item, None, None).name
        == 'Rick Astley - Never Gonna Give You Up (Official Video).mp4'
    )


@pytest.mark.parametrize(
    'numbering,name', [(False, 'Пропаганда - Мелом.mp3'), (True, '003 - Пропаганда - Мелом.mp3')]
)
def test_playlist_numbering_is_opt_in(tmp_path, numbering, name):
    req = replace(
        music(tmp_path, numbering=numbering),
        playlist=PlaylistPosition('PLO5Q7HxgkOYo', 3, 'Sound City'),
    )
    path = output_path(req, track(artists=['Пропаганда'], track='Мелом'), None, None)
    assert path == tmp_path / 'YouTube' / 'Sound City [PLO5Q7HxgkOYo]' / name


def test_identity_separates_media_and_quality(tmp_path):
    item = track()
    video = DownloadRequest(parse_url('https://youtu.be/OaXj5OMqYtE'), DownloadOptions(tmp_path))
    assert media_identity(music(tmp_path), item) != media_identity(video, item)
    assert media_identity(video, item) != media_identity(
        replace(video, options=replace(video.options, max_height=360)), item
    )
    assert media_identity(video, item) != media_identity(video, track('BBBBBBBBBBB'))


def test_old_settings_and_queue_options_without_numbering_still_decode(tmp_path):
    raw = encode_options(DownloadOptions(tmp_path))
    assert raw['numbering'] is False and decode_options(raw).numbering is False
    raw.pop('numbering')
    assert decode_options(raw) == DownloadOptions(tmp_path)
    with pytest.raises(ValueError):
        decode_options(dict(raw, numbering='yes'))


def test_request_key_is_unchanged_unless_numbering_is_enabled(tmp_path):
    req = DownloadRequest(parse_url('https://youtu.be/dQw4w9WgXcQ'), DownloadOptions(tmp_path))
    options = asdict(req.options)
    options.pop('numbering')
    options['folder'] = os.path.normcase(str(req.options.folder))
    legacy = {
        'service': req.link.service,
        'kind': req.link.kind,
        'id': req.link.canonical_id,
        'options': options,
        'selection': None,
        'profile_limit': req.profile_limit,
        'playlist': None,
    }
    assert (
        request_key(req)
        == hashlib.sha256(
            json.dumps(legacy, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
    )
    assert request_key(replace(req, options=replace(req.options, numbering=True))) != request_key(
        req
    )
