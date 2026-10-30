"""Actual provider → media pipeline → local HTTP/FFmpeg, no live platform claims."""

import copy
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import shutil
import subprocess
from threading import Thread

import pytest
from yt_dlp import YoutubeDL

from clipflow.domain.events import (
    CancellationToken,
    FilesSaved,
    RequestsDiscovered,
    StageChanged,
    TitleChanged,
)
from clipflow.domain.models import DownloadOptions, DownloadRequest, JobState
from clipflow.domain.urls import parse_url
from clipflow.providers.base import ExecutionContext
from clipflow.providers.media import MediaPipeline
from clipflow.providers.youtube import YouTubeProvider


class Auth:
    def options_for(self, profile, url):
        return {'http_headers': {'X-Test-Session': 'synthetic-session'}}


@pytest.fixture(scope='module')
def server(tmp_path_factory):
    root = tmp_path_factory.mktemp('youtube-http')
    ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    assert ffmpeg and ffprobe
    subprocess.run(
        [
            ffmpeg,
            '-v',
            'error',
            '-f',
            'lavfi',
            '-i',
            'color=c=blue:s=96x64:r=10',
            '-f',
            'lavfi',
            '-i',
            'sine=frequency=440:sample_rate=48000',
            '-t',
            '0.4',
            '-c:v',
            'libx264',
            '-c:a',
            'aac',
            '-y',
            str(root / 'source.mp4'),
        ],
        check=True,
    )

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.headers.get('X-Test-Session') != 'synthetic-session':
                self.send_error(403)
                return
            super().do_GET()

    http = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(root)))
    thread = Thread(target=http.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{http.server_port}/source.mp4', ffprobe
    http.shutdown()
    http.server_close()
    thread.join(timeout=3)


def metadata(url, identity):
    return {
        '_type': 'video',
        'id': identity,
        'title': 'Название ролика',
        'url': url,
        'ext': 'mp4',
        'vcodec': 'h264',
        'acodec': 'aac',
        'width': 96,
        'height': 64,
        'webpage_url': f'https://www.youtube.com/watch?v={identity}',
    }


@pytest.mark.parametrize('fmt', ['mp4', 'mp3'])
def test_real_single_video_or_music_track(tmp_path, monkeypatch, server, fmt):
    url, ffprobe = server
    info = metadata(url, 'track_A')

    def extract(self, page, download=False):
        return copy.deepcopy(info)

    monkeypatch.setattr(YoutubeDL, 'extract_info', extract)
    events = []
    ctx = ExecutionContext(CancellationToken(), events.append, Auth())
    host = 'music.youtube.com' if fmt == 'mp3' else 'www.youtube.com'
    req = DownloadRequest(
        parse_url(f'https://{host}/watch?v=track_A'),
        DownloadOptions(tmp_path, format=fmt, auth_profile='youtube'),
    )
    result = YouTubeProvider(MediaPipeline()).execute(req, ctx)
    assert len(result.files) == 1
    assert result.files[0].name == 'Название ролика.' + fmt
    data = json.loads(
        subprocess.check_output(
            [ffprobe, '-v', 'error', '-show_streams', '-of', 'json', str(result.files[0])]
        )
    )
    assert {s['codec_type'] for s in data['streams']} == (
        {'audio'} if fmt == 'mp3' else {'video', 'audio'}
    )
    states = [e.state for e in events if isinstance(e, StageChanged)]
    assert states == [JobState.PROBING, JobState.DOWNLOADING, JobState.PROCESSING]
    assert isinstance(events[-1], FilesSaved)
    assert 'synthetic-session' not in repr(result) + repr(events)


def test_mp3_ignores_stale_format_selection_left_by_probe(tmp_path, monkeypatch, server):
    # extract_info(download=False) keeps its default bestvideo+bestaudio choice; reusing it gave HTTP403.
    url, ffprobe = server
    audio = {
        'format_id': '251',
        'url': url,
        'ext': 'mp4',
        'vcodec': 'none',
        'acodec': 'aac',
        'protocol': 'http',
    }
    video = {
        'format_id': '399',
        'url': url.replace('source.mp4', 'forbidden.mp4'),
        'ext': 'mp4',
        'vcodec': 'h264',
        'acodec': 'none',
        'height': 64,
        'protocol': 'http',
    }
    info = {
        '_type': 'video',
        'id': 'track_A',
        'title': 'Название ролика',
        'formats': [video, audio],
        'format_id': '399+251',
        'requested_formats': [video, audio],
        'webpage_url': 'https://music.youtube.com/watch?v=track_A',
    }
    monkeypatch.setattr(
        YoutubeDL, 'extract_info', lambda self, page, download=False: copy.deepcopy(info)
    )
    ctx = ExecutionContext(CancellationToken(), lambda event: None, Auth())
    req = DownloadRequest(
        parse_url('https://music.youtube.com/watch?v=track_A'),
        DownloadOptions(tmp_path, format='mp3'),
    )
    result = YouTubeProvider(MediaPipeline()).execute(req, ctx)
    data = json.loads(
        subprocess.check_output(
            [ffprobe, '-v', 'error', '-show_streams', '-of', 'json', str(result.files[0])]
        )
    )
    assert result.files[0].suffix == '.mp3' and {s['codec_type'] for s in data['streams']} == {
        'audio'
    }


@pytest.mark.parametrize('fmt', ['mp3', 'mp4'])
def test_same_artist_title_gets_numbered_copy_and_retry_reuses_own_file(
    tmp_path, monkeypatch, server, fmt
):
    url, ffprobe = server

    def extract(self, page, download=False):
        info = metadata(url, parse_url(page).canonical_id)
        return dict(info, artists=['Пропаганда'], track='Мелом')

    monkeypatch.setattr(YoutubeDL, 'extract_info', extract)
    events = []
    ctx = ExecutionContext(CancellationToken(), events.append, Auth())
    provider = YouTubeProvider(MediaPipeline())

    def run(identity):
        return provider.execute(
            DownloadRequest(
                parse_url(f'https://www.youtube.com/watch?v={identity}'),
                DownloadOptions(tmp_path, format=fmt),
            ),
            ctx,
        ).files[0]

    first = run('track_A')
    second = run('track_B')
    assert (
        first.name == f'Пропаганда - Мелом.{fmt}' and second.name == f'Пропаганда - Мелом (2).{fmt}'
    )
    names = [e.title for e in events if isinstance(e, TitleChanged)]
    assert names[0] == 'Пропаганда - Мелом' and names[-1] == 'Пропаганда - Мелом (2)'
    foreign = tmp_path / 'YouTube' / f'Пропаганда - Мелом (3).{fmt}'
    foreign.write_bytes(b'not media')
    third = run('track_C')
    assert third.name == f'Пропаганда - Мелом (4).{fmt}' and foreign.read_bytes() == b'not media'
    third.unlink()
    foreign.unlink()
    modified = first.stat().st_mtime_ns
    assert run('track_A') == first and first.stat().st_mtime_ns == modified
    assert run('track_B') == second
    tags = json.loads(
        subprocess.check_output([ffprobe, '-v', 'error', '-show_format', '-of', 'json', str(first)])
    )['format'].get('tags', {})
    assert any(str(value).startswith('clipflow:') for value in tags.values())
    assert sorted(p.name for p in first.parent.iterdir()) == sorted([first.name, second.name])


def test_playlist_children_save_with_original_001_numbers(tmp_path, monkeypatch, server):
    url, _ = server

    def extract(self, page, download=False):
        if 'playlist?' in page:
            return {
                '_type': 'playlist',
                'id': 'PL_test',
                'entries': [
                    {'_type': 'url', 'id': 'one', 'url': 'one', 'title': 'Первый'},
                    None,
                    {'_type': 'url', 'id': 'three', 'url': 'three', 'title': 'Третий'},
                ],
            }
        return metadata(url, parse_url(page).canonical_id)

    monkeypatch.setattr(YoutubeDL, 'extract_info', extract)
    events = []
    ctx = ExecutionContext(CancellationToken(), events.append, Auth())
    req = DownloadRequest(
        parse_url('https://music.youtube.com/playlist?list=PL_test'),
        DownloadOptions(tmp_path, format='mp3', numbering=True),
    )
    provider = YouTubeProvider(MediaPipeline())
    parent = provider.execute(req, ctx)
    assert parent.files == () and parent.discovered_count == 2
    children = [r for e in events if isinstance(e, RequestsDiscovered) for r in e.requests]
    results = [provider.execute(r, ctx) for r in children]
    assert [result.files[0].name for result in results] == [
        '001 - Название ролика.mp3',
        '003 - Название ролика.mp3',
    ]
    for r in results:
        modified = r.files[0].stat().st_mtime_ns
        child = children[results.index(r)]
        assert provider.execute(child, ctx).files == r.files
        assert r.files[0].stat().st_mtime_ns == modified
