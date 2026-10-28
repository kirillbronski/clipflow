"""Read exported/protected cookies into memory; never write a user's export."""
from contextlib import contextmanager
from copy import copy
from http.cookiejar import LoadError
from io import StringIO
from pathlib import Path

from yt_dlp import YoutubeDL


class SessionAuth:
    """An in-memory metadata session handed to transfers, never a saved profile."""
    def __init__(self, options, jar):
        self.options = {k:v for k,v in options.items() if k not in {'cookiefile','_cookies_source','cookiesfrombrowser','username','password'}}
        self.jar = jar

    def options_for(self, profile, url):
        return dict(self.options, _cookiejar=self.jar)


def _cookie_text(source):
    # yt-dlp prints malformed Netscape rows directly, bypassing its logger.
    # Validate before giving it a row that could contain account secrets.
    try:
        text = Path(source).read_text(encoding='utf-8-sig')
        lines = text.splitlines()
        if not lines or lines[0] not in {'# Netscape HTTP Cookie File', '# HTTP Cookie File'}:
            raise ValueError
        for line in lines[1:]:
            if line.startswith('#HttpOnly_'):
                line = line[len('#HttpOnly_'):]
            elif line.startswith('#') or not line.strip():
                continue
            fields = line.split('\t')
            if len(fields) != 7:
                raise ValueError
            domain, include, path, secure, expires, name, value = fields
            if (not domain or any(c.isspace() for c in domain) or include not in {'TRUE','FALSE'}
                    or secure not in {'TRUE','FALSE'} or not path.startswith('/')
                    or (include == 'TRUE') != domain.startswith('.')
                    or (expires and not expires.isascii()) or (expires and not expires.isdigit())
                    or any(ord(c) < 32 or ord(c) == 127 for field in fields for c in field)):
                raise ValueError
        return text
    except (ValueError, TypeError, OSError):
        raise LoadError('Invalid or unreadable cookie export') from None


@contextmanager
def open_downloader(options, *, instagram_context=None, instagram_kind='metadata'):
    options = dict(options)
    source = options.pop('_cookies_source', None) or options.pop('cookiefile', None)
    # Remove both aliases even when the first one was present.
    options.pop('cookiefile', None)
    jar = options.pop('_cookiejar', None)
    if instagram_context is not None:
        from clipflow.providers.instagram_transport import InstagramDownloader
        downloader = InstagramDownloader(options,instagram_context,instagram_kind)
    else:
        downloader = YoutubeDL(options)
    with downloader as ydl:
        if source:
            ydl.cookiejar.load(StringIO(_cookie_text(source)), ignore_discard=True, ignore_expires=True)
        if jar is not None:
            for cookie in jar:
                ydl.cookiejar.set_cookie(copy(cookie))
        yield ydl
