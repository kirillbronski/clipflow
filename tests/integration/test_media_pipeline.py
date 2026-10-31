"""Real HTTP transfers and FFmpeg; only fault injection replaces OS operations."""

import json
import shutil
import subprocess
import sys
import time
from dataclasses import replace
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread, Timer

import pytest

from clipflow.domain.events import (
    CancellationToken,
    FilesSaved,
    ProgressChanged,
    StageChanged,
    WorkCancelled,
)
from clipflow.domain.models import DownloadOptions, DownloadRequest, JobState
from clipflow.domain.paths import PostIdentity
from clipflow.domain.urls import parse_url
from clipflow.providers.base import ExecutionContext, MediaFailure, MediaItem
from clipflow.providers.media import MediaPipeline


class NoAuth:
    def options_for(self, profile, url):
        return {}


@pytest.fixture
def context():
    from tests.instagram_fixtures import Gate

    events = []
    return ExecutionContext(CancellationToken(), events.append, NoAuth(), Gate()), events


@pytest.fixture(scope='module')
def tools():
    ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    assert ffmpeg and ffprobe, 'Native FFmpeg and FFprobe are required for T4 acceptance'
    return ffmpeg, ffprobe


@pytest.fixture(scope='module')
def media_server(tmp_path_factory, tools):
    root = tmp_path_factory.mktemp('media-http')
    source = root / 'sample.mp4'
    subprocess.run(
        [
            tools[0],
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
            str(source),
        ],
        check=True,
    )
    compatible = root / 'compatible.webm'
    subprocess.run(
        [
            tools[0],
            '-v',
            'error',
            '-i',
            str(source),
            '-c:v',
            'libvpx-vp9',
            '-c:a',
            'libopus',
            '-y',
            str(compatible),
        ],
        check=True,
    )
    subprocess.run(
        [
            tools[0],
            '-v',
            'error',
            '-i',
            str(source),
            '-an',
            '-c:v',
            'copy',
            '-y',
            str(root / 'video-only.mp4'),
        ],
        check=True,
    )
    subprocess.run(
        [
            tools[0],
            '-v',
            'error',
            '-i',
            str(source),
            '-vn',
            '-c:a',
            'copy',
            '-y',
            str(root / 'audio.m4a'),
        ],
        check=True,
    )
    # A real tiny PNG; larger payload lets the cancellation test leave a partial.
    subprocess.run(
        [
            tools[0],
            '-v',
            'error',
            '-f',
            'lavfi',
            '-i',
            'color=c=red:s=8x8',
            '-frames:v',
            '1',
            '-y',
            str(root / 'photo.png'),
        ],
        check=True,
    )
    (root / 'large.jpg').write_bytes(b'photo-byte-stream' * 20000)
    (root / 'empty.jpg').write_bytes(b'')

    class Handler(SimpleHTTPRequestHandler):
        hits = 0
        ranges = []
        paths = []

        def log_message(self, *args):
            pass

        def do_GET(self):
            type(self).hits += 1
            type(self).paths.append(self.path)
            if self.path == '/protected.png':
                if self.headers.get('Referer') != 'https://www.instagram.com/':
                    self.send_error(403)
                    return
                self.path = '/photo.png'
            if self.path == '/resume.jpg':
                data = (root / 'large.jpg').read_bytes()
                range_header = self.headers.get('Range')
                type(self).ranges.append(range_header)
                start = int(range_header[6:-1]) if range_header else 0
                if start >= len(data):
                    self.send_response(416)
                    self.send_header('Content-Range', f'bytes */{len(data)}')
                    self.end_headers()
                    return
                self.send_response(206 if start else 200)
                self.send_header('Content-Length', str(len(data) - start))
                self.send_header('Content-Range', f'bytes {start}-{len(data) - 1}/{len(data)}')
                self.end_headers()
                self.wfile.write(data[start:])
                return
            super().do_GET()

    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(root)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_port}', root, Handler
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


def request(tmp_path, fmt='mp4', **options):
    return DownloadRequest(
        parse_url('https://www.instagram.com/p/ABC/'),
        DownloadOptions(tmp_path, format=fmt, **options),
    )


def item(url, kind='video', ext='mp4', **info):
    return MediaItem(
        'media1',
        3,
        kind,
        'Проверка',
        {
            'id': 'media1',
            'title': 'Проверка',
            'url': url,
            'ext': ext,
            'post_code': 'ABC',
            'author': 'alice',
            'post_title': 'Пост',
            **info,
        },
    )


def probe(path, tools):
    data = json.loads(
        subprocess.check_output(
            [tools[1], '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)],
            text=True,
            encoding='utf-8',
        )
    )
    assert Path(data['format']['filename']) == path
    return data


def test_mp3_uses_320k_audio_only(tmp_path, context, media_server, tools):
    ctx, _ = context
    base, _, _ = media_server
    req = request(tmp_path, 'mp3')
    pipeline = MediaPipeline(ffmpeg=tools[0], ffprobe=tools[1])
    path = pipeline.save(item(base + '/sample.mp4'), req, ctx)[0]
    streams = probe(path, tools)['streams']
    assert {stream['codec_type'] for stream in streams} == {'audio'}
    assert streams[0]['codec_name'] == 'mp3' and int(streams[0]['bit_rate']) == 320000


def test_music_downloads_best_audio_without_fetching_video(tmp_path, context, media_server, tools):
    ctx, _ = context
    base, _, handler = media_server
    before = len(handler.paths)
    req = DownloadRequest(
        parse_url('https://music.youtube.com/watch?v=track'), DownloadOptions(tmp_path)
    )
    media = MediaItem(
        'track',
        1,
        'video',
        'Best audio',
        {
            'id': 'track',
            'title': 'Best audio',
            'formats': [
                {
                    'format_id': 'video',
                    'url': base + '/video-only.mp4',
                    'ext': 'mp4',
                    'vcodec': 'h264',
                    'acodec': 'none',
                    'height': 720,
                },
                {
                    'format_id': 'low',
                    'url': base + '/never-low.m4a',
                    'ext': 'm4a',
                    'vcodec': 'none',
                    'acodec': 'aac',
                    'abr': 64,
                },
                {
                    'format_id': 'audio',
                    'url': base + '/audio.m4a',
                    'ext': 'm4a',
                    'vcodec': 'none',
                    'acodec': 'aac',
                    'abr': 128,
                },
            ],
        },
    )
    path = MediaPipeline(ffmpeg=tools[0], ffprobe=tools[1]).save(media, req, ctx)[0]
    assert '/audio.m4a' in handler.paths[before:]
    assert (
        '/video-only.mp4' not in handler.paths[before:]
        and '/never-low.m4a' not in handler.paths[before:]
    )
    assert path.suffix == '.mp3' and {s['codec_type'] for s in probe(path, tools)['streams']} == {
        'audio'
    }


@pytest.mark.parametrize(
    'fmt,container,codecs',
    [
        ('mp4', 'mp4', {'h264', 'aac'}),
        ('mkv', 'matroska', {'h264', 'aac'}),
        ('webm', 'webm', {'vp9', 'opus'}),
        ('mp3', 'mp3', {'mp3'}),
    ],
)
def test_native_containers_and_repeat_preserves_finished_file(
    tmp_path, context, media_server, tools, fmt, container, codecs
):
    ctx, events = context
    base, _, handler = media_server
    req = request(tmp_path, fmt)
    pipeline = MediaPipeline(ffmpeg=tools[0], ffprobe=tools[1])
    paths = pipeline.save(item(base + '/sample.mp4'), req, ctx)
    assert len(paths) == 1 and paths[0].name == '03.' + fmt
    data = probe(paths[0], tools)
    assert container in data['format']['format_name']
    assert {s['codec_name'] for s in data['streams']} == codecs
    video = [s for s in data['streams'] if s['codec_type'] == 'video']
    if video:
        assert (video[0]['width'], video[0]['height']) == (96, 64)
    modified = paths[0].stat().st_mtime_ns
    hits = handler.hits
    assert pipeline.save(item(base + '/sample.mp4'), req, ctx) == paths
    assert paths[0].stat().st_mtime_ns == modified
    assert handler.hits == hits
    assert any(isinstance(e, ProgressChanged) for e in events)
    assert any(isinstance(e, StageChanged) and e.state == JobState.PROCESSING for e in events)
    assert any(isinstance(e, FilesSaved) and e.files == paths for e in events)
    assert sorted(p.name for p in paths[0].parent.iterdir()) == ['03.' + fmt]


def test_compatible_webm_is_remuxed_without_changing_packets(
    tmp_path, context, media_server, tools
):
    ctx, _ = context
    base, root, _ = media_server
    (final,) = MediaPipeline().save(
        item(base + '/compatible.webm', ext='webm'), request(tmp_path, 'webm'), ctx
    )

    def packet_hashes(path):
        result = subprocess.check_output(
            [
                tools[1],
                '-v',
                'error',
                '-show_packets',
                '-show_data_hash',
                'sha256',
                '-of',
                'json',
                str(path),
            ],
            text=True,
            encoding='utf-8',
        )
        return [(p['stream_index'], p['data_hash']) for p in json.loads(result)['packets']]

    assert packet_hashes(final) == packet_hashes(root / 'compatible.webm')


def test_photo_original_bytes_extension_and_atomic_caption(tmp_path, context, media_server):
    ctx, events = context
    base, root, _ = media_server
    paths = MediaPipeline().save(
        item(base + '/photo.png', 'photo', 'png', description='Полный текст\nВторая строка'),
        request(tmp_path, description='txt'),
        ctx,
    )
    assert [p.name for p in paths] == ['03.png', '03.txt']
    assert paths[0].read_bytes() == (root / 'photo.png').read_bytes()
    assert paths[1].read_text(encoding='utf-8-sig') == 'Полный текст\nВторая строка'
    assert not list(paths[0].parent.glob('*.tmp'))


def test_caption_replace_failure_preserves_previous_file(
    tmp_path, context, media_server, monkeypatch
):
    from clipflow.providers import media

    ctx, events = context
    base, _, _ = media_server
    req = request(tmp_path, description='md')
    pipeline = MediaPipeline()
    _, caption = pipeline.save(
        item(base + '/photo.png', 'photo', 'png', description='Прежний текст'), req, ctx
    )
    events.clear()
    real_replace = media.os.replace

    def failed(source, target):
        if Path(target).suffix == '.md':
            raise OSError('disk unavailable')
        return real_replace(source, target)

    monkeypatch.setattr(media.os, 'replace', failed)
    with pytest.raises(MediaFailure) as error:
        pipeline.save(
            item(base + '/photo.png', 'photo', 'png', description='Новый текст'), req, ctx
        )
    assert error.value.code == 'write_failed'
    assert caption.read_text(encoding='utf-8') == 'Прежний текст'
    assert not any(isinstance(e, FilesSaved) for e in events)
    assert not list(caption.parent.glob('*.tmp'))


def test_disk_full_never_reports_success(tmp_path, context, media_server, monkeypatch):
    from clipflow.providers import media

    ctx, events = context
    base, _, _ = media_server

    def disk_full(*args):
        raise OSError(28, 'No space left')

    monkeypatch.setattr(media.os, 'replace', disk_full)
    with pytest.raises(MediaFailure) as error:
        MediaPipeline().save(item(base + '/photo.png', 'photo', 'png'), request(tmp_path), ctx)
    assert error.value.code == 'write_failed'
    assert not any(isinstance(e, FilesSaved) for e in events)
    assert not list(tmp_path.rglob('03.png'))


def test_cancel_retains_partial_and_next_run_finishes(tmp_path, context, media_server):
    ctx, events = context
    base, root, _ = media_server

    def cancel_after_chunk(event):
        events.append(event)
        if isinstance(event, ProgressChanged):
            ctx.cancel.cancel('pause')

    cancelling = replace(ctx, emit=cancel_after_chunk)
    pipeline = MediaPipeline()
    with pytest.raises(WorkCancelled):
        pipeline.save(item(base + '/large.jpg', 'photo', 'jpg'), request(tmp_path), cancelling)
    partials = list(tmp_path.rglob('*.part'))
    assert (
        len(partials) == 1 and 0 < partials[0].stat().st_size < (root / 'large.jpg').stat().st_size
    )
    assert not any(isinstance(e, FilesSaved) for e in events)
    completed = pipeline.save(
        item(base + '/large.jpg', 'photo', 'jpg'),
        request(tmp_path),
        replace(ctx, cancel=CancellationToken()),
    )
    assert completed[0].read_bytes() == (root / 'large.jpg').read_bytes()
    assert not list(tmp_path.rglob('*.part'))


def test_ffmpeg_failure_is_typed_and_never_publishes_result(tmp_path, context, media_server):
    ctx, events = context
    base, _, _ = media_server
    with pytest.raises(MediaFailure) as error:
        MediaPipeline(ffmpeg='missing-ffmpeg-executable').save(
            item(base + '/sample.mp4'), request(tmp_path), ctx
        )
    assert error.value.code == 'tool_missing'
    assert not any(isinstance(e, FilesSaved) for e in events)
    assert not list(tmp_path.rglob('03.mp4'))


def test_missing_url_is_safe_failure(tmp_path, context):
    ctx, events = context
    with pytest.raises(MediaFailure) as error:
        MediaPipeline().save(
            MediaItem('bad', 1, 'photo', '', {'ext': 'jpg'}), request(tmp_path), ctx
        )
    assert error.value.code == 'invalid_media'
    assert not any(isinstance(e, FilesSaved) for e in events)


def test_range_resume_and_full_partial_after_pause(tmp_path, context, media_server):
    from clipflow.domain.paths import output_path

    ctx, _ = context
    base, root, handler = media_server
    req = request(tmp_path)
    media = item(base + '/resume.jpg', 'photo', 'jpg')
    target = output_path(req, media, 'alice', PostIdentity('ABC', 'Пост', None))
    target.parent.mkdir(parents=True)
    payload = (root / 'large.jpg').read_bytes()
    partial_path = Path(str(target) + '.part')
    partial_path.write_bytes(payload[:1234])
    (final,) = MediaPipeline().save(media, req, ctx)
    assert final.read_bytes() == payload
    assert handler.ranges[-1] == 'bytes=1234-'
    final.unlink()
    partial_path.write_bytes(payload)
    (final,) = MediaPipeline().save(media, req, ctx)
    assert final.read_bytes() == payload
    assert not partial_path.exists()


def test_video_cancel_keeps_source_partial(tmp_path, context, media_server):
    ctx, events = context
    base, _, _ = media_server

    def pause(event):
        events.append(event)
        if isinstance(event, ProgressChanged) and event.downloaded_bytes:
            ctx.cancel.cancel('pause')

    with pytest.raises(WorkCancelled):
        MediaPipeline().save(
            item(base + '/sample.mp4'), request(tmp_path), replace(ctx, emit=pause)
        )
    assert any(p.stat().st_size for p in tmp_path.rglob('*.part'))
    assert not any(isinstance(e, FilesSaved) for e in events)
    result = MediaPipeline().save(
        item(base + '/sample.mp4'), request(tmp_path), replace(ctx, cancel=CancellationToken())
    )
    assert result[0].is_file()


def test_cancel_before_processing_keeps_raw_source_for_retry(tmp_path, context, media_server):
    ctx, _ = context
    base, _, handler = media_server

    def pause(event):
        if isinstance(event, StageChanged) and event.state == JobState.PROCESSING:
            ctx.cancel.cancel('pause')

    with pytest.raises(WorkCancelled):
        MediaPipeline().save(
            item(base + '/sample.mp4'), request(tmp_path), replace(ctx, emit=pause)
        )
    assert list(tmp_path.rglob('*.source.mp4'))
    hits = handler.hits
    result = MediaPipeline().save(
        item(base + '/sample.mp4'), request(tmp_path), replace(ctx, cancel=CancellationToken())
    )
    assert result[0].is_file()
    assert handler.hits == hits


def test_empty_photo_and_download_failure_are_not_success(tmp_path, context, media_server):
    ctx, events = context
    base, _, _ = media_server
    with pytest.raises(MediaFailure, match='incomplete_download'):
        MediaPipeline().save(item(base + '/empty.jpg', 'photo', 'jpg'), request(tmp_path), ctx)
    with pytest.raises(MediaFailure, match='download_failed') as error:
        MediaPipeline().save(
            item(base + '/missing.jpg?secret=not-for-logs', 'photo', 'jpg'), request(tmp_path), ctx
        )
    assert 'secret' not in str(error.value)
    assert not any(isinstance(e, FilesSaved) for e in events)


def test_failed_conversion_and_corrupt_existing_file_preserved(tmp_path, context, media_server):
    from clipflow.domain.paths import output_path

    ctx, events = context
    base, _, _ = media_server
    req = request(tmp_path)
    broken = item(base + '/large.jpg')
    with pytest.raises(MediaFailure, match='invalid_media|processing_failed'):
        MediaPipeline().save(broken, req, ctx)
    target = output_path(req, broken, 'alice', PostIdentity('ABC', 'Пост', None))
    target.write_bytes(b'foreign corrupt data')
    with pytest.raises(MediaFailure):
        MediaPipeline().save(item(base + '/sample.mp4'), req, ctx)
    assert target.read_bytes() == b'foreign corrupt data'
    assert not any(isinstance(e, FilesSaved) for e in events)


def test_adaptive_video_and_audio_merge_and_height_limit(tmp_path, context, media_server, tools):
    ctx, _ = context
    base, _, _ = media_server
    media = MediaItem(
        'adaptive',
        1,
        'video',
        'Adaptive streams',
        {
            'formats': [
                {
                    'format_id': 'video',
                    'url': base + '/video-only.mp4',
                    'ext': 'mp4',
                    'vcodec': 'h264',
                    'acodec': 'none',
                    'height': 64,
                    'width': 96,
                },
                {
                    'format_id': 'audio',
                    'url': base + '/audio.m4a',
                    'ext': 'm4a',
                    'vcodec': 'none',
                    'acodec': 'aac',
                },
            ]
        },
    )
    req = DownloadRequest(
        parse_url('https://youtu.be/BaW_jenozKc'), DownloadOptions(tmp_path, max_height=64)
    )
    (final,) = MediaPipeline().save(media, req, ctx)
    assert final.name == 'Adaptive streams.mp4'
    assert {s['codec_name'] for s in probe(final, tools)['streams']} == {'h264', 'aac'}
    limited = replace(req, options=replace(req.options, folder=tmp_path / 'limited', max_height=32))
    with pytest.raises(MediaFailure):
        MediaPipeline().save(media, limited, ctx)
    assert not list((tmp_path / 'limited').rglob('*.mp4'))


def test_disk_full_when_opening_partial_is_typed(tmp_path, context, media_server, monkeypatch):
    ctx, events = context
    base, _, _ = media_server
    original = Path.open

    def open_file(path, *args, **kwargs):
        if path.suffix == '.part':
            raise OSError(28, 'Disk full')
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', open_file)
    with pytest.raises(MediaFailure, match='write_failed'):
        MediaPipeline().save(item(base + '/photo.png', 'photo', 'png'), request(tmp_path), ctx)
    assert not any(isinstance(e, FilesSaved) for e in events)


@pytest.mark.parametrize('failure', [OSError(28, 'Disk full'), RuntimeError('socket closed')])
def test_cancel_during_download_is_reported_as_cancel_not_failure(
    tmp_path, context, media_server, monkeypatch, failure
):
    ctx, events = context
    base, _, _ = media_server
    original = Path.open

    def interrupted(path, *args, **kwargs):
        if path.suffix == '.part':
            ctx.cancel.cancel('pause')  # the user paused; the transfer then breaks
            raise failure
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', interrupted)
    with pytest.raises(WorkCancelled):
        MediaPipeline().save(item(base + '/photo.png', 'photo', 'png'), request(tmp_path), ctx)
    assert not any(isinstance(e, FilesSaved) for e in events)


def test_cancellation_reaps_processing_child(context, monkeypatch):
    from clipflow.providers import processes

    ctx, _ = context
    real_popen = subprocess.Popen
    children = []

    def observed_popen(*args, **kwargs):
        child = real_popen(*args, **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(processes.subprocess, 'Popen', observed_popen)
    timer = Timer(0.25, lambda: ctx.cancel.cancel('shutdown'))
    timer.start()
    start = time.monotonic()
    try:
        with pytest.raises(WorkCancelled):
            MediaPipeline._run([sys.executable, '-c', 'import time; time.sleep(30)'], ctx)
    finally:
        timer.cancel()
        timer.join()
    assert time.monotonic() - start < 3
    assert children and all(child.poll() is not None for child in children)


def test_photo_uses_extractor_required_headers(tmp_path, context, media_server):
    ctx, _ = context
    base, root, _ = media_server
    media = item(
        base + '/protected.png',
        'photo',
        'png',
        http_headers={'Referer': 'https://www.instagram.com/'},
    )
    (final,) = MediaPipeline().save(media, request(tmp_path), ctx)
    assert final.read_bytes() == (root / 'photo.png').read_bytes()


def test_same_title_videos_publish_separate_media_and_captions(
    media_server, tmp_path, context, tools
):
    base, source, _ = media_server
    ctx, events = context
    pipeline = MediaPipeline(ffmpeg=tools[0], ffprobe=tools[1])
    first = MediaItem(
        'AAAAAAAAAAA',
        1,
        'video',
        'Introduction',
        {'url': base + '/sample.mp4', 'ext': 'mp4', 'description': 'First video'},
    )
    second = replace(first, id='BBBBBBBBBBB', info=dict(first.info, description='Second video'))
    req = DownloadRequest(
        parse_url('https://youtu.be/AAAAAAAAAAA'), DownloadOptions(tmp_path, description='txt')
    )
    old = tmp_path / 'YouTube/Introduction.mp4'
    old.parent.mkdir()
    shutil.copy2(source / 'sample.mp4', old)  # Untagged legacy output belongs to an unknown source.
    original = old.read_bytes()
    a = pipeline.save(first, req, ctx)
    b = pipeline.save(second, replace(req, link=parse_url('https://youtu.be/BBBBBBBBBBB')), ctx)
    assert a[0] != b[0] and a[0] != old and b[0] != old
    assert a[1].read_text(encoding='utf-8-sig').strip() == 'First video'
    assert b[1].read_text(encoding='utf-8-sig').strip() == 'Second video'
    assert old.read_bytes() == original
    assert pipeline.save(first, req, ctx) == a
    assert a[0].is_file() and b[0].is_file()
