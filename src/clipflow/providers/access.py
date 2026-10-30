"""Read exported/protected cookies into memory; never write a user's export."""

import os
from contextlib import contextmanager
from copy import copy
from http.cookiejar import LoadError
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

from yt_dlp import YoutubeDL
from yt_dlp.networking.common import Response


class SessionAuth:
    """An in-memory metadata session handed to transfers, never a saved profile."""

    def __init__(self, options, jar):
        self.options = {
            k: v
            for k, v in options.items()
            if k
            not in {'cookiefile', '_cookies_source', 'cookiesfrombrowser', 'username', 'password'}
        }
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
                line = line[len('#HttpOnly_') :]
            elif line.startswith('#') or not line.strip():
                continue
            fields = line.split('\t')
            if len(fields) != 7:
                raise ValueError
            domain, include, path, secure, expires, name, value = fields
            if (
                not domain
                or any(c.isspace() for c in domain)
                or include not in {'TRUE', 'FALSE'}
                or secure not in {'TRUE', 'FALSE'}
                or not path.startswith('/')
                or (include == 'TRUE') != domain.startswith('.')
                or (expires and not expires.isascii())
                or (expires and not expires.isdigit())
                or any(ord(c) < 32 or ord(c) == 127 for field in fields for c in field)
            ):
                raise ValueError
        return text
    except (ValueError, TypeError, OSError):
        raise LoadError('Invalid or unreadable cookie export') from None


class _CancellableResponse(Response):
    def __init__(self, response, cancel):
        super().__init__(
            response,
            response.url,
            response.headers,
            response.status,
            response.reason,
            response.extensions,
        )
        self.cancel = cancel

    def read(self, amt=None):
        try:
            self.cancel.raise_if_cancelled()
            data = self.fp.read(amt)
            self.cancel.raise_if_cancelled()
            return data
        except BaseException:
            self.close()
            self.cancel.raise_if_cancelled()
            raise


class _CancellableDownloader(YoutubeDL):
    def __init__(self, options, cancel):
        self.cancel = cancel
        self._responses = []
        super().__init__(options)

    def urlopen(self, request):
        self.cancel.raise_if_cancelled()
        try:
            response = super().urlopen(request)
        except BaseException:
            self.cancel.raise_if_cancelled()
            raise
        wrapped = _CancellableResponse(response, self.cancel)
        self._responses.append(wrapped)
        try:
            self.cancel.raise_if_cancelled()
        except BaseException:
            wrapped.close()
            raise
        return wrapped

    def close(self):
        try:
            for response in self._responses:
                response.close()
            self._responses.clear()
        finally:
            super().close()

    def run_pp(self, pp, info):
        # yt-dlp's internal merger/fixup bypasses MediaPipeline._convert.
        # Adapt only this processor instance; never patch global Popen/yt-dlp.
        from yt_dlp.postprocessor.ffmpeg import FFmpegPostProcessor

        if not isinstance(pp, FFmpegPostProcessor):
            return super().run_pp(pp, info)
        original = pp.real_run_ffmpeg

        def run(inputs, outputs, *, expected_retcodes=(0,)):
            from clipflow.providers.media import MediaPipeline

            self.cancel.raise_if_cancelled()
            pp.check_version()
            inputs = tuple(inputs)
            outputs = tuple(outputs)
            args = [pp.executable, '-nostdin', '-y', '-loglevel', 'error']
            for kind, paths in (('i', inputs), ('o', outputs)):
                for number, (path, options) in enumerate(paths, 1):
                    if not path:
                        continue
                    keys = [f'_{kind}{number}', f'_{kind}']
                    if kind == 'o' and number == 1:
                        keys.append('')
                    args.extend(options)
                    if kind == 'o':
                        args.extend(['-movflags', '+faststart'])
                    args.extend(pp._configuration_args(pp.basename, keys))
                    if kind == 'i':
                        args.append('-i')
                    args.append(pp._ffmpeg_filename_argument(path))
            result = MediaPipeline._run(
                args,
                SimpleNamespace(cancel=self.cancel),
                capture_error=True,
                expected_retcodes=expected_retcodes,
            )
            modified = min(os.stat(path).st_mtime for path, _ in inputs if path)
            for path, _ in outputs:
                if path:
                    pp.try_utime(path, modified, modified)
            return result.decode('utf-8', errors='replace')

        pp.real_run_ffmpeg = run
        try:
            return super().run_pp(pp, info)
        finally:
            pp.real_run_ffmpeg = original


@contextmanager
def open_downloader(options, *, context=None, instagram_context=None, instagram_kind='metadata'):
    options = dict(options)
    context = context or instagram_context
    if context is not None:
        # A blocking socket operation finishes within this timeout. Cancellation
        # is checked before retry logic can start another request.
        options['socket_timeout'] = min(float(options.get('socket_timeout') or 5), 5)
    source = options.pop('_cookies_source', None) or options.pop('cookiefile', None)
    # Remove both aliases even when the first one was present.
    options.pop('cookiefile', None)
    jar = options.pop('_cookiejar', None)
    if instagram_context is not None:
        from clipflow.providers.instagram_transport import InstagramDownloader

        downloader = InstagramDownloader(options, instagram_context, instagram_kind)
    elif context is not None:
        downloader = _CancellableDownloader(options, context.cancel)
    else:
        downloader = YoutubeDL(options)
    with downloader as ydl:
        if source:
            ydl.cookiejar.load(
                StringIO(_cookie_text(source)), ignore_discard=True, ignore_expires=True
            )
        if jar is not None:
            for cookie in jar:
                ydl.cookiejar.set_cookie(copy(cookie))
        yield ydl
