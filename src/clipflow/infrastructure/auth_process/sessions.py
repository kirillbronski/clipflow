"""Protected snapshots, compatible with existing session.dat cookie-list payloads."""

import json
import os
import time
from http.cookiejar import Cookie, CookieJar
from pathlib import Path
from tempfile import NamedTemporaryFile

from clipflow.domain.models import Service

DOMAINS = {Service.YOUTUBE: 'youtube.com', Service.INSTAGRAM: 'instagram.com'}
AUTH_NAMES = {
    Service.YOUTUBE: ('SAPISID', '__Secure-3PAPISID', '__Secure-1PAPISID'),
    Service.INSTAGRAM: ('sessionid',),
}
FOLDERS = {Service.YOUTUBE: 'YouTubeAuth', Service.INSTAGRAM: 'InstagramAuth'}
# Sign-in browser modes: the saved key (also the USER_AGENTS key) and its label key.
AUTH_MODES = (
    ('Обычный Qt WebEngine', 'auth_native_mode'),
    ('Chrome на iPad · 51', 'auth_ipad51'),
    ('Chrome на iPad · 87', 'auth_ipad87'),
)


def atomic_protected(path, payload, protect):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    encrypted = protect(json.dumps(payload, ensure_ascii=False).encode('utf-8'))
    temporary = None
    try:
        with NamedTemporaryFile(dir=path.parent, prefix='.protected-', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(encrypted)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def load_protected(path, protect):
    try:
        raw = Path(path).read_bytes()
        if len(raw) > 16 * 1024 * 1024:
            return None
        return json.loads(protect(raw, decrypt=True))
    except (OSError, ValueError, TypeError):
        return None


def scoped_cookies(cookies, domain):
    if not isinstance(cookies, list):
        return []
    result = []
    for item in cookies:
        if not isinstance(item, dict):
            continue
        host = item.get('domain', '')
        if not isinstance(host, str) or not (
            host.lstrip('.').lower() == domain or host.lower().endswith('.' + domain)
        ):
            continue
        if not all(isinstance(item.get(key), str) for key in ('name', 'value', 'path')):
            continue
        expiry = item.get('expires', -1)
        if type(expiry) not in (int, float) or (expiry >= 0 and expiry <= time.time()):
            continue
        if not item['path'].startswith('/') or any(
            '\0' in item[key] for key in ('name', 'value', 'path')
        ):
            continue
        result.append(
            {
                key: item.get(key)
                for key in ('domain', 'name', 'value', 'path', 'expires', 'secure', 'httpOnly')
            }
        )
    return result


def cookie_jar(cookies):
    jar = CookieJar()
    for item in cookies:
        expiry = item.get('expires', -1)
        domain = item['domain']
        jar.set_cookie(
            Cookie(
                0,
                item['name'],
                item['value'],
                None,
                False,
                domain,
                domain.startswith('.'),
                domain.startswith('.'),
                item['path'],
                True,
                bool(item.get('secure')),
                int(expiry) if expiry > 0 else None,
                expiry <= 0,
                None,
                None,
                {'HttpOnly': bool(item.get('httpOnly'))},
                False,
            )
        )
    return jar


class SessionStore:
    def __init__(self, directory, service, protect):
        self.directory = Path(directory)
        self.service = service
        self.protect = protect
        self.snapshot = self.directory / 'session.dat'

    def saved(self):
        if (self.directory / 'logout-request').exists():
            return []
        cookies = scoped_cookies(load_protected(self.snapshot, self.protect), DOMAINS[self.service])
        return (
            cookies
            if any(c['name'] in AUTH_NAMES[self.service] and c['value'] for c in cookies)
            else []
        )

    def save(self, cookies):
        if (self.directory / 'logout-request').exists():
            return False
        cookies = scoped_cookies(cookies, DOMAINS[self.service])
        if not any(c['name'] in AUTH_NAMES[self.service] and c['value'] for c in cookies):
            return False
        atomic_protected(self.snapshot, cookies, self.protect)
        return True

    def logout(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / 'logout-request').write_text('sign out', encoding='ascii')
        self.snapshot.unlink(missing_ok=True)
