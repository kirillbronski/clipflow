import copy
import shutil
import subprocess
from dataclasses import replace
from functools import partial
from http.cookiejar import Cookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

from clipflow.domain.events import FilesSaved
from clipflow.providers.instagram_post import (
    InstagramExtractor,
    InstagramMediaFailure,
    InstagramPostProvider,
)
from clipflow.providers.media import MediaPipeline
from tests.instagram_fixtures import context, isolate_instagram, product, request


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    isolate_instagram(monkeypatch)


@pytest.fixture
def tmp_path(tmp_path_factory):
    # Keep these transfer scenarios below the production portable path limit.
    # macOS's long per-user temp root + pytest's full test name otherwise makes
    # them path-rejection tests before any HTTP/media behavior is exercised.
    return tmp_path_factory.mktemp('ig-files')


@pytest.fixture(scope='module')
def http_media(tmp_path_factory):
    root = tmp_path_factory.mktemp('instagram-local')
    ffmpeg = shutil.which('ffmpeg')
    assert ffmpeg
    subprocess.run(
        [
            ffmpeg,
            '-v',
            'error',
            '-f',
            'lavfi',
            '-i',
            'color=c=red:s=8x8',
            '-frames:v',
            '1',
            '-y',
            str(root / 'image.png'),
        ],
        check=True,
    )
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
            str(root / 'video.mp4'),
        ],
        check=True,
    )

    class Handler(SimpleHTTPRequestHandler):
        throttled = 0

        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path == '/session.png':
                if 'metadata-session=synthetic-value' not in (self.headers.get('Cookie') or ''):
                    self.send_error(403)
                    return
                self.path = '/image.png'
            if self.path == '/throttled.png':
                type(self).throttled += 1
                (root / 'throttled-count').write_text(str(type(self).throttled))
                self.send_response(429)
                self.send_header('Retry-After', '120')
                self.end_headers()
                return
            if self.headers.get('Referer') != 'https://www.instagram.com/':
                self.send_error(403)
                return
            super().do_GET()

    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(root)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_port}', root
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


def extracted(monkeypatch, data):
    monkeypatch.setattr(
        InstagramExtractor,
        '_real_extract',
        lambda self, url: self._extract_product(copy.deepcopy(data), get_comments=False),
    )


@pytest.mark.parametrize('fmt', ['txt', 'md'])
def test_mixed_photo_video_numbering_and_paired_txt_md(tmp_path, monkeypatch, http_media, fmt):
    base, root = http_media
    extracted(monkeypatch, product(base))
    ctx, events, gate = context()
    result = InstagramPostProvider(MediaPipeline()).execute(request(tmp_path, description=fmt), ctx)
    assert [p.name for p in result.files] == [
        '01.png',
        '01.' + fmt,
        '02.mp4',
        '02.' + fmt,
        '03.png',
        '03.' + fmt,
    ]
    assert result.files[0].read_bytes() == (root / 'image.png').read_bytes()
    for caption in result.files[1::2]:
        assert caption.read_text(encoding='utf-8-sig') == 'Подпись — полностью\nВторая строка'
    assert gate.calls == ['cdn', 'cdn', 'cdn', 'completed']
    assert len([e for e in events if isinstance(e, FilesSaved)]) == 3
    assert '2026-10-28' in str(result.files[0].parent)


@pytest.mark.parametrize(
    'author_folder,post_folder', [(True, True), (True, False), (False, True), (False, False)]
)
def test_author_and_post_folder_options_independent(
    tmp_path, monkeypatch, http_media, author_folder, post_folder
):
    base, _ = http_media
    extracted(monkeypatch, product(base))
    ctx, _, _ = context()
    req = request(
        tmp_path, author_folder=author_folder, post_folder=post_folder, media_filter='photo'
    )
    result = InstagramPostProvider(MediaPipeline()).execute(req, ctx)
    relative = result.files[0].relative_to(tmp_path / 'Instagram')
    assert ('alice' in relative.parts) == author_folder
    assert len(relative.parts) == 1 + int(author_folder) + int(post_folder)
    assert [p.name for p in result.files] == (
        ['01.png', '03.png'] if post_folder else ['ABC - 01.png', 'ABC - 03.png']
    )


@pytest.mark.parametrize(
    'caption,fmt', [(None, 'txt'), ('', 'md'), ('   ', 'txt'), ('Not saved', None)]
)
def test_caption_missing_or_disabled(tmp_path, monkeypatch, http_media, caption, fmt):
    base, _ = http_media
    data = product(base)
    data['caption'] = {'text': caption}
    extracted(monkeypatch, data)
    ctx, _, _ = context()
    result = InstagramPostProvider(MediaPipeline()).execute(
        request(tmp_path, description=fmt, media_filter='photo'), ctx
    )
    assert len(result.files) == 2
    assert not list(tmp_path.rglob('*.txt')) and not list(tmp_path.rglob('*.md'))


@pytest.mark.parametrize('post_folder', [True, False])
def test_second_untitled_post_same_author_safe(tmp_path, monkeypatch, http_media, post_folder):
    base, _ = http_media
    data = product(base)
    data['caption'] = None
    extracted(monkeypatch, data)
    ctx, _, _ = context()
    provider = InstagramPostProvider(MediaPipeline())
    req = request(tmp_path, post_folder=post_folder, media_filter='photo')
    first = provider.execute(req, ctx)
    modified = first.files[0].stat().st_mtime_ns
    other = provider.execute(
        request(
            tmp_path, 'https://instagram.com/p/XYZ/', post_folder=post_folder, media_filter='photo'
        ),
        ctx,
    )
    assert not set(first.files) & set(other.files)
    assert first.files[0].stat().st_mtime_ns == modified


def test_failed_item_has_diagnostic_and_keeps_finished_files(tmp_path, monkeypatch, http_media):
    base, _ = http_media
    data = product(base)
    data['carousel_media'][1]['video_versions'][0]['url'] = base + '/missing.mp4'
    extracted(monkeypatch, data)
    ctx, events, gate = context()
    provider = InstagramPostProvider(MediaPipeline())
    req = request(tmp_path, description='txt')
    with pytest.raises(InstagramMediaFailure) as error:
        provider.execute(req, ctx)
    assert error.value.index == 2 and error.value.reason == 'download_failed'
    saved = [p for e in events if isinstance(e, FilesSaved) for p in e.files]
    assert [p.name for p in saved] == ['01.png', '01.txt']
    assert all(p.is_file() for p in saved)
    modified = saved[0].stat().st_mtime_ns
    assert 'completed' not in gate.calls
    extracted(monkeypatch, product(base))
    result = provider.execute(req, ctx)
    assert len(result.files) == 6 and saved[0].stat().st_mtime_ns == modified


def test_file_429_stops_without_success_or_implicit_retries(tmp_path, monkeypatch, http_media):
    from clipflow.application.instagram_rate_policy import InstagramDeferred

    base, root = http_media
    data = product(base)
    data['carousel_media'][0]['image_versions2']['candidates'][-1]['url'] = base + '/throttled.png'
    extracted(monkeypatch, data)
    ctx, events, gate = context()
    with pytest.raises(InstagramDeferred) as error:
        InstagramPostProvider(MediaPipeline()).execute(request(tmp_path), ctx)
    assert error.value.decision.reason == 'rate_limit'
    assert not any(isinstance(e, FilesSaved) for e in events)
    assert 'completed' not in gate.calls
    assert (root / 'throttled-count').read_text() == '1'


def test_description_write_failure_is_tied_to_media_item(tmp_path, monkeypatch, http_media):
    from clipflow.providers import media

    base, _ = http_media
    extracted(monkeypatch, product(base))
    original = media.os.replace

    def fail_caption(source, target):
        if Path(target).suffix == '.txt':
            raise OSError(28, 'disk full')
        return original(source, target)

    monkeypatch.setattr(media.os, 'replace', fail_caption)
    ctx, events, _ = context()
    with pytest.raises(InstagramMediaFailure) as error:
        InstagramPostProvider(MediaPipeline()).execute(request(tmp_path, description='txt'), ctx)
    assert error.value.index == 1 and error.value.reason == 'write_failed'
    assert not any(isinstance(e, FilesSaved) for e in events)
    assert len(list(tmp_path.rglob('01.png'))) == 1


def test_metadata_session_cookie_is_used_by_photo_transfer(tmp_path, monkeypatch, http_media):
    base, root = http_media
    data = product(base)
    data['carousel_media'][0]['image_versions2']['candidates'][-1]['url'] = base + '/session.png'

    def extract(self, url):
        self._downloader.cookiejar.set_cookie(
            Cookie(
                0,
                'metadata-session',
                'synthetic-value',
                None,
                False,
                '127.0.0.1',
                False,
                False,
                '/',
                True,
                False,
                None,
                True,
                None,
                None,
                {},
            )
        )
        return self._extract_product(copy.deepcopy(data), get_comments=False)

    monkeypatch.setattr(InstagramExtractor, '_real_extract', extract)
    ctx, events, _ = context()
    result = InstagramPostProvider(MediaPipeline()).execute(
        request(tmp_path, media_filter='photo'), ctx
    )
    assert result.files[0].read_bytes() == (root / 'image.png').read_bytes()
    assert 'synthetic-value' not in repr(result) + repr(events)
