"""Lesson/player extraction with synthetic school pages and real media transfers."""

import base64
from dataclasses import replace
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from http.cookiejar import Cookie
import json
from pathlib import Path
import shutil
import subprocess
from threading import Thread
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
from yt_dlp import YoutubeDL
from yt_dlp.cookies import YoutubeDLCookieJar

from clipflow.domain.events import (
    CancellationToken,
    FilesSaved,
    RequestsDiscovered,
    SelectionRequired,
    WorkCancelled,
)
from clipflow.domain.models import ContentKind, DownloadOptions, DownloadRequest
from clipflow.domain.urls import parse_url
from clipflow.providers.base import ExecutionContext, MediaFailure
from clipflow.providers.media import MediaPipeline
from clipflow.providers.getcourse import GetCourseProvider, LessonExtractor, PlayerExtractor

FIXTURES = Path(__file__).parents[1] / 'fixtures/getcourse'
LESSON = 'https://school.getcourse.ru/pl/teach/control/lesson/view?id=123'
PLAYER = 'https://player02.getcourse.ru/sign-player/?json=eyJ2aWRlb19oYXNoIjoiZmlyc3QifQ=='


class Auth:
    def __init__(self, **options):
        self.options = options

    def options_for(self, profile, url):
        return dict(self.options)


def request(folder, url=LESSON, selection=None, **options):
    return DownloadRequest(parse_url(url), DownloadOptions(folder, **options), selection=selection)


def context(**auth):
    events = []
    return ExecutionContext(CancellationToken(), events.append, Auth(**auth)), events


@pytest.fixture
def school(monkeypatch):
    state = {
        'html': (FIXTURES / 'lesson.html').read_text(encoding='utf-8'),
        'login_ok': True,
        'redirect': False,
        'posts': [],
        'cookies_seen': [],
        'resolved_hash': None,
        'formats': [
            {
                'format_id': '720',
                'url': 'https://cdn.example.test/lesson.mp4',
                'ext': 'mp4',
                'vcodec': 'h264',
                'acodec': 'aac',
                'height': 720,
            }
        ],
        'denied': set(),
    }

    def webpage(self, url, *args, **kwargs):
        if '/cms/system/login' in url:
            return (FIXTURES / 'login.html').read_text(encoding='utf-8')
        data = json.loads(base64.b64decode(parse_qs(urlparse(url).query)['json'][0]))
        if data['video_hash'] in state['denied']:
            from yt_dlp.utils import ExtractorError

            raise ExtractorError('Private player synthetic-secret', expected=True)
        info = json.loads(
            (FIXTURES / 'player.html').read_text().split('window.configs = ')[1].split(';')[0]
        )
        info['videoHash'] = state['resolved_hash'] or data['video_hash']
        info['gcFileId'] = 12345 if data['video_hash'] == 'first' else 67890
        return '<script>window.configs = ' + json.dumps(info) + ';</script>'

    def page_handle(self, url, *args, **kwargs):
        state['cookies_seen'].append({c.name: c.value for c in self._downloader.cookiejar})
        return state['html'], SimpleNamespace(
            url='https://school.getcourse.ru/cms/system/login' if state['redirect'] else url
        )

    def login_json(self, url, *args, **kwargs):
        state['posts'].append(parse_qs(kwargs['data'].decode()))
        self._downloader.cookiejar.set_cookie(
            Cookie(
                0,
                'school-auth',
                'authorized',
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
        return {
            'data': {
                'success': state['login_ok'],
                'errorMessage': '' if state['login_ok'] else 'Bad password synthetic-secret',
            }
        }

    monkeypatch.setattr(LessonExtractor, '_download_webpage_handle', page_handle)
    monkeypatch.setattr(LessonExtractor, '_download_webpage', webpage)
    monkeypatch.setattr(LessonExtractor, '_download_json', login_json)
    monkeypatch.setattr(PlayerExtractor, '_download_webpage', webpage)
    monkeypatch.setattr(
        PlayerExtractor,
        '_extract_m3u8_formats_and_subtitles',
        lambda *a, **kw: (state['formats'], {}),
    )
    return state


@pytest.mark.parametrize(
    'host', ['player02.getcourse.ru', 'cf-api-2.vhcdn.com', 'cf-api-2.gceuproxy.com']
)
def test_direct_player(tmp_path, school, host):
    ctx, _ = context()
    req = request(tmp_path, PLAYER.replace('player02.getcourse.ru', host))
    assert req.link.kind == ContentKind.PLAYER
    result = GetCourseProvider(MediaPipeline()).probe(req, ctx)
    assert len(result.items) == 1 and result.items[0].id == '12345'
    assert result.items[0].title == 'Видео GetCourse'
    assert result.available_heights == (720,)
    assert not result.selection_required


def test_lesson_all_items(tmp_path, school):
    ctx, _ = context()
    result = GetCourseProvider(MediaPipeline()).probe(request(tmp_path), ctx)
    assert [item.id for item in result.items] == ['first', 'second']
    assert [item.index for item in result.items] == [1, 2]
    assert all(
        'Урок 1' in item.title and 'Основы звука и развитие музыки' in item.title
        for item in result.items
    )
    assert 'Разбор' in result.items[0].title and 'Практика' in result.items[1].title
    assert result.selection_required


def test_selection_required_and_selected_ids(tmp_path, school):
    ctx, events = context()
    provider = GetCourseProvider(MediaPipeline())
    result = provider.execute(request(tmp_path), ctx)
    assert result.files == () and result.discovered_count == 0
    assert [e.ids for e in events if isinstance(e, SelectionRequired)] == [('first', 'second')]
    assert not any(isinstance(e, FilesSaved) for e in events)
    events.clear()
    result = provider.execute(request(tmp_path, selection=('first', 'second')), ctx)
    children = [r for e in events if isinstance(e, RequestsDiscovered) for r in e.requests]
    assert result.discovered_count == 2 and result.files == ()
    assert [r.selection for r in children] == [('first',), ('second',)]
    assert all(r.label for r in children) and children[0].label != children[1].label
    assert all(r.link == parse_url(LESSON) for r in children)


@pytest.mark.parametrize('redirect,bad_login', [(True, False), (False, True)])
def test_school_login_error_not_instagram_hint(tmp_path, school, redirect, bad_login, capsys):
    school['redirect'] = redirect
    school['login_ok'] = not bad_login
    ctx, _ = context(username='student@example.test', password='synthetic-secret')
    with pytest.raises(MediaFailure) as error:
        GetCourseProvider(MediaPipeline()).probe(request(tmp_path, auth_profile='school'), ctx)
    assert error.value.code == 'getcourse_school_login_required'
    assert 'instagram' not in str(error.value).lower() and 'brave' not in str(error.value).lower()
    output = capsys.readouterr()
    assert 'synthetic-secret' not in str(error.value) + repr(error.value) + output.out + output.err


def test_signed_school_login_uses_server_timestamp(tmp_path, school):
    ctx, _ = context(username='student@example.test', password='synthetic-secret')
    GetCourseProvider(MediaPipeline()).probe(request(tmp_path, auth_profile='school'), ctx)
    post = school['posts'][0]
    assert post['requestTime'] == ['1700000123']
    assert post['requestSimpleSign'] == ['abcdef1234']
    assert post['xdgetId'] == ['77']
    assert post['params[email]'] == ['student@example.test']


def test_source_cookie_export_is_not_overwritten(tmp_path, school):
    source = tmp_path / 'export.txt'
    source.write_text(
        '# Netscape HTTP Cookie File\n.school.getcourse.ru\tTRUE\t/\tTRUE\t0\tsession\tsynthetic-cookie\n',
        encoding='utf-8',
    )
    original = source.read_bytes()
    modified = source.stat().st_mtime_ns
    ctx, _ = context(cookiefile=str(source))
    GetCourseProvider(MediaPipeline()).probe(request(tmp_path, auth_profile='export'), ctx)
    assert source.read_bytes() == original and source.stat().st_mtime_ns == modified
    assert school['cookies_seen'][-1]['session'] == 'synthetic-cookie'


def test_metadata_change_rejects_missing_selection(tmp_path, school):
    ctx, events = context()
    provider = GetCourseProvider(MediaPipeline())
    assert provider.probe(request(tmp_path), ctx).items[0].id == 'first'
    school['html'] = school['html'].replace(
        'eyJ2aWRlb19oYXNoIjoiZmlyc3QifQ==', 'eyJ2aWRlb19oYXNoIjoibmV3In0='
    )
    with pytest.raises(MediaFailure, match='getcourse_selection_changed'):
        provider.execute(request(tmp_path, selection=('first',)), ctx)
    assert not any(isinstance(e, FilesSaved) for e in events)


def test_selection_uses_identity_after_reorder(tmp_path, school):
    ctx, _ = context()
    # Signed timestamps/signatures can change; video identity must not.
    school['html'] = school['html'].replace('synthetic-signature', 'new-signature')
    result = GetCourseProvider(MediaPipeline()).probe(request(tmp_path, selection=('second',)), ctx)
    assert [i.id for i in result.items] == ['second']
    assert 'Практика' in result.items[0].title


def test_no_login_has_no_login_side_effect(tmp_path, school):
    ctx, _ = context()
    GetCourseProvider(MediaPipeline()).probe(request(tmp_path), ctx)
    assert school['posts'] == []


@pytest.fixture(scope='module')
def media_http(tmp_path_factory):
    root = tmp_path_factory.mktemp('getcourse-http')
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
            str(root / 'media.mp4'),
        ],
        check=True,
    )

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path == '/protected.mp4':
                if 'school-auth=authorized' not in (self.headers.get('Cookie') or ''):
                    self.send_error(403)
                    return
                self.path = '/media.mp4'
            super().do_GET()

    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(root)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_port}/media.mp4'
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


def test_one_material_error_keeps_other_child_downloadable(tmp_path, school, media_http):
    school['formats'] = [
        {
            'format_id': 'best',
            'url': media_http,
            'ext': 'mp4',
            'vcodec': 'h264',
            'acodec': 'aac',
            'height': 64,
        }
    ]
    ctx, events = context()
    provider = GetCourseProvider(MediaPipeline())
    provider.execute(request(tmp_path, selection=('first', 'second')), ctx)
    children = [r for e in events if isinstance(e, RequestsDiscovered) for r in e.requests]
    school['denied'].add('first')
    with pytest.raises(MediaFailure):
        provider.execute(children[0], ctx)
    result = provider.execute(children[1], ctx)
    assert len(result.files) == 1 and result.files[0].is_file()
    assert result.files[0].name.startswith('02 - Урок 1')
    assert 'second' not in result.files[0].name


def test_wrong_service_and_cancel_are_safe(tmp_path, school):
    ctx, _ = context()
    with pytest.raises(MediaFailure, match='invalid_request'):
        GetCourseProvider(MediaPipeline()).probe(request(tmp_path, 'https://youtu.be/test'), ctx)
    ctx.cancel.cancel('pause')
    with pytest.raises(WorkCancelled):
        GetCourseProvider(MediaPipeline()).probe(request(tmp_path), ctx)


def test_email_session_survives_into_media_transfer(tmp_path, school, media_http):
    school['formats'] = [
        {
            'format_id': 'best',
            'url': media_http.replace('media.mp4', 'protected.mp4'),
            'ext': 'mp4',
            'vcodec': 'h264',
            'acodec': 'aac',
            'height': 64,
        }
    ]
    ctx, events = context(username='student@example.test', password='synthetic-secret')
    result = GetCourseProvider(MediaPipeline()).execute(
        request(tmp_path, selection=('second',), auth_profile='school-ref'), ctx
    )
    assert result.files[0].is_file()
    assert 'synthetic-secret' not in repr(result) + repr(events)


def test_browser_cookies_are_read_through_gateway_without_real_browser(
    tmp_path, school, monkeypatch
):
    from yt_dlp import cookies

    jar = YoutubeDLCookieJar()
    jar.set_cookie(
        Cookie(
            0,
            'browser-session',
            'synthetic-browser-cookie',
            None,
            False,
            '.school.getcourse.ru',
            True,
            True,
            '/',
            True,
            True,
            None,
            True,
            None,
            None,
            {},
        )
    )
    monkeypatch.setattr(cookies, 'extract_cookies_from_browser', lambda *a, **k: jar)
    ctx, _ = context(cookiesfrombrowser=('firefox',))
    GetCourseProvider(MediaPipeline()).probe(request(tmp_path, auth_profile='browser-ref'), ctx)
    assert school['cookies_seen'][-1]['browser-session'] == 'synthetic-browser-cookie'


def test_changed_player_config_rejects_selected_identity(tmp_path, school):
    school['resolved_hash'] = 'replacement-video'
    ctx, events = context()
    with pytest.raises(MediaFailure, match='getcourse_selection_changed'):
        GetCourseProvider(MediaPipeline()).probe(request(tmp_path, selection=('first',)), ctx)
    assert not any(isinstance(e, FilesSaved) for e in events)


def test_two_lessons_and_direct_players_cannot_share_finished_file(tmp_path):
    from clipflow.domain.paths import output_path
    from clipflow.providers.base import MediaItem

    item = MediaItem('12345', 1, 'video', 'Видео GetCourse', {})
    a = output_path(request(tmp_path), item, None, None)
    b = output_path(request(tmp_path, LESSON.replace('id=123', 'id=456')), item, None, None)
    assert a != b
    a = output_path(request(tmp_path, PLAYER), item, None, None)
    b = output_path(request(tmp_path, PLAYER), replace(item, id='67890'), None, None)
    assert a != b


def test_empty_or_unidentifiable_lesson_is_not_success(tmp_path, school):
    ctx, events = context()
    school['html'] = '<html><title>Пустой урок</title></html>'
    with pytest.raises(MediaFailure, match='getcourse_no_media'):
        GetCourseProvider(MediaPipeline()).execute(request(tmp_path), ctx)
    assert not any(isinstance(e, (FilesSaved, RequestsDiscovered)) for e in events)


@pytest.mark.parametrize(
    'text',
    [
        'not a Netscape file synthetic-secret',
        '# Netscape HTTP Cookie File\ninvalid row synthetic-secret',
        '# Netscape HTTP Cookie File\n.test\tTRUE\t/\tTRUE\tbad-expiry\tsession\tsynthetic-secret',
        '# Netscape HTTP Cookie File\n.test\tFALSE\t/\tTRUE\t0\tsession\tsynthetic-secret',
    ],
)
def test_bad_cookie_export_has_school_specific_safe_error(tmp_path, school, capsys, text):
    source = tmp_path / 'bad-export.txt'
    source.write_text(text, encoding='utf-8')
    ctx, _ = context(cookiefile=str(source))
    with pytest.raises(MediaFailure, match='getcourse_auth_failed') as error:
        GetCourseProvider(MediaPipeline()).probe(request(tmp_path), ctx)
    output = capsys.readouterr()
    assert 'synthetic-secret' not in str(error.value) + output.out + output.err
    assert source.read_text() == text


def test_http_403_reports_getcourse_access_denied(tmp_path, school, monkeypatch):
    from io import BytesIO
    from yt_dlp.networking.common import Response
    from yt_dlp.networking.exceptions import HTTPError

    def denied(*args, **kwargs):
        raise HTTPError(Response(BytesIO(b''), url=PLAYER, headers={}, status=403))

    monkeypatch.setattr(PlayerExtractor, '_download_webpage', denied)
    ctx, _ = context()
    with pytest.raises(MediaFailure, match='getcourse_access_denied'):
        GetCourseProvider(MediaPipeline()).probe(request(tmp_path, PLAYER), ctx)


def test_duplicate_embeds_do_not_duplicate_selection_ids(tmp_path, school):
    frame = school['html'].split('<iframe')[1].split('</iframe>')[0]
    school['html'] += '<iframe' + frame + '</iframe>'
    ctx, _ = context()
    assert [
        i.id for i in GetCourseProvider(MediaPipeline()).probe(request(tmp_path), ctx).items
    ] == ['first', 'second']


@pytest.mark.parametrize(
    'html',
    [
        '<iframe src="https://player02.getcourse.ru/sign-player/?json=bad"></iframe>',
        '<iframe src="https://cf-api-2.gceuproxy.com/sign-player/?json=e30="></iframe>',
    ],
)
def test_unstable_player_identity_is_not_silently_guessed(tmp_path, school, html):
    school['html'] = html
    ctx, _ = context()
    with pytest.raises(MediaFailure, match='getcourse_invalid_player'):
        GetCourseProvider(MediaPipeline()).probe(request(tmp_path), ctx)


def test_cancel_on_selection_never_continues_to_download(tmp_path, school):
    ctx, events = context()

    def emit(event):
        events.append(event)
        if isinstance(event, SelectionRequired):
            ctx.cancel.cancel('pause')

    with pytest.raises(WorkCancelled):
        GetCourseProvider(MediaPipeline()).execute(request(tmp_path), replace(ctx, emit=emit))
    assert not any(isinstance(e, FilesSaved) for e in events)


@pytest.mark.parametrize(
    'url',
    [
        'https://evil.gceuproxy.com.evil.test/sign-player/?json=x',
        'https://cf-api-2.gceuproxy.com/not-player?json=x',
    ],
)
def test_regional_player_lookalikes_are_not_routed_as_getcourse(url):
    from clipflow.domain.urls import InvalidLink

    with pytest.raises(InvalidLink):
        parse_url(url)
