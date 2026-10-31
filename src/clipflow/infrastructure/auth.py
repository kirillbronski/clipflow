"""Scoped protected authentication and supervised, separate browser processes."""

import contextlib
import hashlib
import os
import re
import subprocess
import sys
import time
from copy import copy
from dataclasses import dataclass, field
from http.cookiejar import MozillaCookieJar
from io import StringIO
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from clipflow.domain.models import ContentKind, Service
from clipflow.domain.urls import parse_url
from clipflow.infrastructure.auth_process.sessions import (
    FOLDERS,
    SessionStore,
    atomic_protected,
    cookie_jar,
    load_protected,
)
from clipflow.infrastructure.platform import PlatformServices
from clipflow.providers.base import MediaFailure

BROWSERS = (
    'chrome',
    'edge',
    'brave',
    'firefox',
    'opera',
    'opera_gx',
    'safari',
    'vivaldi',
    'chromium',
    'yandex',
    'whale',
)


@dataclass(frozen=True)
class AuthStatus:
    service: Service
    profile: str | None = None
    connected: bool = False
    state: str = 'signed_out'
    account: str | None = field(default=None, repr=False)


class AuthProcessHandle:
    def __init__(self, gateway, service, process, directory, instance_id):
        self.gateway = gateway
        self.service = service
        self.process = process
        self.directory = directory
        self.close_path = directory / ('close-request-' + instance_id)
        self._deadline = None
        self._terminated = False

    def close(self):
        if self.process.poll() is not None or self._deadline is not None:
            return
        try:
            self.close_path.write_text('close', encoding='ascii')
        except OSError:
            self.process.terminate()
            self._terminated = True
        self._deadline = time.monotonic() + 3

    def poll(self):
        if (
            self.process.poll() is None
            and self._deadline is not None
            and time.monotonic() >= self._deadline
        ):
            if self._terminated:
                self.process.kill()
            else:
                self.process.terminate()
                self._terminated = True
            self._deadline = time.monotonic() + 2
        status = self.gateway.status(self.service)
        if self.process.poll() is None:
            return AuthStatus(
                status.service,
                status.profile,
                status.connected,
                'closing' if self._deadline is not None else 'pending',
                status.account,
            )
        with contextlib.suppress(OSError):
            self.close_path.unlink(missing_ok=True)
        return status


class NativeAuthGateway:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir).resolve()
        self.platform = PlatformServices(self.data_dir)
        self.sessions = {
            s: SessionStore(self.data_dir / name, s, self.platform.protect)
            for s, name in FOLDERS.items()
        }
        self._handles = {}
        self._selected_gc = None
        self._closing = False

    def activate_profile(self, service, profile):
        if service == Service.GETCOURSE:
            self._selected_gc = profile

    def _gc_path(self, profile):
        if not isinstance(profile, str) or not re.fullmatch(r'gc-[0-9a-f]{24}', profile):
            raise MediaFailure('auth_scope_mismatch')
        return self.data_dir / 'GetCourseAuth' / (profile + '.dat')

    @staticmethod
    def school(url):
        try:
            link = parse_url(url)
            if link.service != Service.GETCOURSE or link.kind != ContentKind.LESSON:
                raise ValueError
            return urlsplit(link.canonical_url).hostname
        except (ValueError, TypeError):
            raise MediaFailure('auth_invalid_school') from None

    def status(self, service):
        service = Service(service)
        if service in self.sessions:
            profile = service.value + '-default'
            saved = bool(self.sessions[service].saved())
            return AuthStatus(service, profile, saved, 'saved' if saved else 'signed_out')
        if self._selected_gc:
            try:
                payload = load_protected(self._gc_path(self._selected_gc), self.platform.protect)
            except MediaFailure:
                payload = None
            if isinstance(payload, dict) and payload.get('school'):
                return AuthStatus(
                    service, self._selected_gc, True, 'configured', payload.get('email') or None
                )
        return AuthStatus(service)

    def options_for(self, profile, url):  # noqa: C901  # подпроект 3
        if profile is None:
            return {}
        try:
            link = parse_url(url)
            for service, store in self.sessions.items():
                if profile == service.value + '-default':
                    if link.service != service:
                        raise MediaFailure('auth_scope_mismatch')
                    saved = store.saved()
                    if not saved:
                        raise MediaFailure('auth_required')
                    return {'_cookiejar': cookie_jar(saved)}
            if link.service != Service.GETCOURSE:
                raise MediaFailure('auth_scope_mismatch')
            payload = load_protected(self._gc_path(profile), self.platform.protect)
            if not isinstance(payload, dict):
                raise MediaFailure('auth_required')
            # A shared player/CDN host cannot identify a school. Signed/public
            # player links work without releasing another school's credentials.
            if link.kind == ContentKind.PLAYER:
                return {}
            if self.school(url) != payload.get('school'):
                raise MediaFailure('auth_scope_mismatch')
            if payload.get('method') == 'email':
                if not payload.get('email') or not payload.get('password'):
                    raise MediaFailure('auth_required')
                return {'username': payload['email'], 'password': payload['password']}
            if payload.get('method') == 'cookies':
                from clipflow.providers.access import _cookie_text

                jar = MozillaCookieJar()
                jar._really_load(
                    StringIO(_cookie_text(payload['file'])), payload['file'], True, False
                )
            elif payload.get('method') == 'browser':
                from yt_dlp import YoutubeDL
                from yt_dlp.cookies import load_cookies

                class Quiet:
                    def debug(self, *a, **k):
                        pass

                    info = warning = error = debug

                with YoutubeDL({'quiet': True, 'no_warnings': True, 'logger': Quiet()}) as ydl:
                    jar = load_cookies(None, self.browser_source(payload['browser']), ydl)
            else:
                return {}
            scoped = MozillaCookieJar()
            host = payload['school']
            for cookie in jar:
                domain = cookie.domain.lstrip('.').lower()
                if domain == host or domain.endswith('.' + host):
                    scoped.set_cookie(copy(cookie))
            if not tuple(scoped):
                raise MediaFailure('auth_required')
            return {'_cookiejar': scoped}
        except MediaFailure:
            raise
        except Exception:  # noqa: BLE001  # подпроект 3
            raise MediaFailure('auth_required') from None

    @staticmethod
    def browser_source(browser):
        if browser == 'yandex':
            folder = (
                Path.home() / 'Library/Application Support/Yandex/YandexBrowser'
                if sys.platform == 'darwin'
                else Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local')))
                / 'Yandex/YandexBrowser/User Data'
            )
            return 'chrome', str(folder)
        if browser == 'opera_gx':
            folder = (
                Path.home() / 'Library/Application Support/com.operasoftware.OperaGX'
                if sys.platform == 'darwin'
                else Path(os.environ.get('APPDATA', str(Path.home() / 'AppData/Roaming')))
                / 'Opera Software/Opera GX Stable'
            )
            return 'opera', str(folder)
        return (browser,)

    def configure_getcourse(self, url, method, *, email='', password='', file='', browser=''):
        host = self.school(url)
        profile = 'gc-' + hashlib.sha256(host.encode()).hexdigest()[:24]
        if method not in {'email', 'cookies', 'browser', 'public'}:
            raise MediaFailure('auth_invalid_settings')
        if method == 'email' and (not email.strip() or not password):
            raise MediaFailure('auth_invalid_settings')
        if method == 'cookies' and not Path(file).is_file():
            raise MediaFailure('auth_invalid_settings')
        if method == 'browser' and browser not in BROWSERS:
            raise MediaFailure('auth_invalid_settings')
        payload = {
            'school': host,
            'method': method,
            'email': email.strip() if method == 'email' else '',
            'password': password if method == 'email' else '',
            'file': str(Path(file).resolve()) if method == 'cookies' else '',
            'browser': browser if method == 'browser' else '',
        }
        try:
            atomic_protected(self._gc_path(profile), payload, self.platform.protect)
        except Exception:  # noqa: BLE001  # подпроект 3
            raise MediaFailure('auth_storage_failed') from None
        self._selected_gc = profile
        return profile

    def import_legacy_getcourse(self, url):
        legacy = self.data_dir / 'getcourse-profile.dat'
        payload = load_protected(legacy, self.platform.protect)
        if not isinstance(payload, dict):
            raise MediaFailure('auth_required')
        method = payload.get('method')
        browsers = {
            'Google Chrome': 'chrome',
            'Microsoft Edge': 'edge',
            'Brave': 'brave',
            'Mozilla Firefox': 'firefox',
            'Firefox': 'firefox',
            'Opera': 'opera',
            'Opera GX': 'opera_gx',
            'Safari': 'safari',
            'Vivaldi': 'vivaldi',
            'Chromium': 'chromium',
            'Яндекс Браузер': 'yandex',
            'Whale': 'whale',
        }
        normalized = (
            'email'
            if method == 'Email и пароль'
            else 'cookies'
            if method == 'Файл cookies'
            else 'browser'
            if method in browsers
            else None
        )
        if normalized is None:
            raise MediaFailure('auth_invalid_settings')
        return self.configure_getcourse(
            url,
            normalized,
            email=payload.get('email', ''),
            password=payload.get('password', ''),
            file=payload.get('file', ''),
            browser=browsers.get(method, ''),
        )

    def sign_in(self, service, language):
        service = Service(service)
        if self._closing or service not in self.sessions or language not in {'ru', 'en'}:
            raise MediaFailure('auth_unavailable')
        existing = self._handles.get(service)
        if existing is not None and existing.process.poll() is None:
            return existing
        directory = self.sessions[service].directory
        directory.mkdir(parents=True, exist_ok=True)
        instance_id = uuid4().hex
        args = (
            [sys.executable]
            if getattr(sys, 'frozen', False)
            else [sys.executable, '-m', 'clipflow.infrastructure.auth_process']
        )
        args += [
            '--youtube-login' if service == Service.YOUTUBE else '--instagram-login',
            '--language',
            language,
            '--data-dir',
            str(self.data_dir),
            '--instance-id',
            instance_id,
        ]
        try:
            process = subprocess.Popen(
                args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=dict(os.environ)
            )
        except OSError:
            raise MediaFailure('auth_launch_failed') from None
        handle = AuthProcessHandle(self, service, process, directory, instance_id)
        self._handles[service] = handle
        return handle

    def logout(self, profile):
        for service, session in self.sessions.items():
            if profile == service.value + '-default':
                session.logout()
                if service in self._handles:
                    self._handles[service].close()
                return
        path = self._gc_path(profile)
        path.unlink(missing_ok=True)
        if self._selected_gc == profile:
            self._selected_gc = None

    def support_status(self):
        return {
            s.value: {'connected': self.status(s).connected, 'state': self.status(s).state}
            for s in Service
        }

    def poll(self):
        for handle in tuple(self._handles.values()):
            handle.poll()

    def close(self):
        self._closing = True
        for handle in self._handles.values():
            handle.close()

    @property
    def is_closed(self):
        self.poll()
        return all(h.process.poll() is not None for h in self._handles.values())

    def drain(self):
        self.close()
        while not self.is_closed:
            time.sleep(0.025)
