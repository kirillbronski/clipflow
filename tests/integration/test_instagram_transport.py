import contextlib
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest
from yt_dlp.networking import Request

from clipflow.application.instagram_rate_policy import InstagramDeferred
from clipflow.domain.events import RateLimitDeferred
from clipflow.providers.access import open_downloader
from tests.instagram_fixtures import context
from tests.unit.test_instagram_rate_policy import policy


@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        calls = []

        def log_message(self, *args):
            pass

        def do_GET(self):
            self.calls.append(self.path)
            if self.path == '/redirect':
                self.send_response(302)
                self.send_header('Location', '/target')
                self.end_headers()
                return
            data = b'{"status":"ok","data":{}}' if self.path == '/json' else b'abc' * 100000
            self.send_response(429 if self.path == '/429' else 200)
            self.send_header('Retry-After', '2000')
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            with contextlib.suppress(ConnectionError, OSError):
                self.wfile.write(data)

    http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=http.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{http.server_port}', Handler.calls
    http.shutdown()
    http.server_close()
    thread.join(3)


def test_ytdlp_every_http_request_and_stream_lease(tmp_path, server):
    gate, clock, token = policy(tmp_path)
    ctx, events, _ = context()
    ctx = replace(ctx, instagram_rate=gate)
    base, calls = server
    with open_downloader({'quiet': True}, instagram_context=ctx) as ydl:
        with ydl.urlopen(Request(base + '/metadata')) as response:
            assert not gate.store.claim('other', clock.now)
            assert len(response.read()) == 300000
        assert gate.store.claim('other', clock.now)
        gate.store.release('other')
        with ydl.urlopen(Request(base + '/metadata2')) as response:
            response.read()
    assert clock.waits == [3] and len(calls) == 2


def test_ytdlp_redirect_is_also_paced(tmp_path, server):
    gate, clock, _ = policy(tmp_path)
    ctx, _, _ = context()
    ctx = replace(ctx, instagram_rate=gate)
    base, calls = server
    with (
        open_downloader({'quiet': True}, instagram_context=ctx) as ydl,
        ydl.urlopen(Request(base + '/redirect')) as response,
    ):
        response.read()
    assert calls == ['/redirect', '/target'] and clock.waits == [3]


def test_cancel_during_redirect_preserves_cancellation_and_releases_lease(tmp_path, server):
    from clipflow.domain.events import WorkCancelled

    gate, clock, _ = policy(tmp_path)
    ctx, _, _ = context()
    ctx = replace(ctx, instagram_rate=gate)
    base, calls = server
    original = gate.acquire
    acquired = []

    def acquire(kind, token):
        acquired.append(kind)
        if len(acquired) == 2:
            token.cancel('cancel')
        return original(kind, token)

    gate.acquire = acquire
    with (
        open_downloader({'quiet': True}, instagram_context=ctx) as ydl,
        pytest.raises(WorkCancelled),
    ):
        ydl.urlopen(Request(base + '/redirect'))
    assert calls == ['/redirect'] and gate.store.claim('other', clock.now)


def test_cdn_reads_do_not_sleep_and_429_defers_once(tmp_path, server):
    gate, clock, token = policy(tmp_path)
    ctx, events, _ = context()
    ctx = replace(ctx, instagram_rate=gate)
    base, calls = server
    with open_downloader({'quiet': True}, instagram_context=ctx, instagram_kind='cdn') as ydl:
        with ydl.urlopen(Request(base + '/media')) as response:
            while response.read(1024):
                pass
        assert clock.waits == []
        with pytest.raises(InstagramDeferred):
            ydl.urlopen(Request(base + '/429'))
        with pytest.raises(InstagramDeferred):
            ydl.urlopen(Request(base + '/blocked'))
    assert calls == ['/media', '/429']
    assert len([e for e in events if isinstance(e, RateLimitDeferred)]) == 2
    assert gate.store.claim('other', clock.now)


def test_instaloader_copied_session_uses_shared_gate(tmp_path, server):
    import requests

    from clipflow.providers.instagram_profile import PacedSession

    gate, clock, token = policy(tmp_path)
    ctx, events, _ = context()
    ctx = replace(ctx, instagram_rate=gate)
    base, calls = server
    with requests.Session() as original, requests.Session() as cloned:
        PacedSession(original, ctx).get(base + '/one').close()
        with pytest.raises(InstagramDeferred):
            PacedSession(cloned, ctx).get(base + '/429')
    assert clock.waits == [10] and gate.store.load().strikes == 1


def test_instaloader_source_merges_and_marks_exhaustion(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import instaloader

    from clipflow.providers.instagram_profile import InstagramProfileProvider, InstaloaderPageSource
    from tests.unit.test_profile_discovery import codes, post, req

    gate, clock, token = policy(tmp_path)
    ctx, events, _ = context()
    ctx = replace(ctx, instagram_rate=gate)

    def native(i):
        return SimpleNamespace(
            shortcode=f'C{i}', date_utc=post(i).published_at.replace(tzinfo=None)
        )

    profile = SimpleNamespace(
        is_private=False,
        get_posts=lambda: iter([native(1), native(2)]),
        get_reels=lambda: iter([native(2), native(3)]),
    )
    monkeypatch.setattr(instaloader.Profile, 'from_username', lambda *args: profile)
    source = InstaloaderPageSource()
    try:
        InstagramProfileProvider(source).execute(req(tmp_path), ctx)
        assert codes(events) == ['C1', 'C2', 'C3']
        profile.is_private = True
        profile.followed_by_viewer = False
        profile.is_self = False
        with pytest.raises(Exception, match='instagram_access_required'):
            list(source.pages(req(tmp_path), ctx))
    finally:
        source.close()


def test_instaloader_real_get_json_wraps_library_copy_and_homepage(tmp_path, server, monkeypatch):
    from urllib.parse import urlparse

    import requests
    from instaloader.instaloadercontext import copy_session

    from clipflow.providers.instagram_profile import PacedContext

    base, calls = server
    original = requests.Session.request

    def local(self, method, url, **kwargs):
        assert urlparse(url).hostname in {'www.instagram.com', 'i.instagram.com'}
        return original(self, method, base + '/json', **kwargs)

    monkeypatch.setattr(requests.Session, 'request', local)
    gate, clock, _ = policy(tmp_path)
    ctx, _, _ = context()
    ctx = replace(ctx, instagram_rate=gate)
    client = PacedContext(ctx)
    try:
        client._session.get('https://www.instagram.com/').close()
        with copy_session(client._session, 30) as clone:
            assert client.get_json('api/v1/feed', {}, session=clone)['status'] == 'ok'
        assert calls == ['/json', '/json'] and clock.waits == [10]
    finally:
        client.close()


def test_profile_cookie_domains_remain_in_memory(tmp_path, monkeypatch):
    from http.cookiejar import Cookie, CookieJar
    from types import SimpleNamespace

    import instaloader

    from clipflow.providers.instagram_profile import InstaloaderPageSource
    from tests.unit.test_profile_discovery import req

    jar = CookieJar()
    jar.set_cookie(
        Cookie(
            0,
            'sessionid',
            'synthetic-session',
            None,
            False,
            '.instagram.com',
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
            False,
        )
    )

    class Auth:
        def options_for(self, *args):
            return {'_cookiejar': jar}

    gate, clock, _ = policy(tmp_path)
    ctx, _, _ = context()
    ctx = replace(ctx, instagram_rate=gate, auth=Auth())
    monkeypatch.setattr(
        instaloader.Profile,
        'from_username',
        lambda client, name: SimpleNamespace(
            is_private=False, get_posts=lambda: iter(()), get_reels=lambda: iter(())
        ),
    )
    monkeypatch.setattr(instaloader.InstaloaderContext, 'test_login', lambda self: 'alice')
    source = InstaloaderPageSource()
    try:
        assert list(source.pages(req(tmp_path), ctx))[-1].next_cursor is None
        saved = list(source._context._session.cookies)
        assert any(
            c.name == 'sessionid' and c.domain == '.instagram.com' and c.secure for c in saved
        )
        assert not list(tmp_path.rglob('*cookies*'))
    finally:
        source.close()
