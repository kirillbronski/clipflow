"""GetCourse lesson selection and signed school login, with no legacy App dependency."""

import base64
from contextlib import contextmanager
from dataclasses import replace
from html.parser import HTMLParser
from http.cookiejar import LoadError
import json
import re
from urllib.parse import parse_qs, urljoin, urlparse

from yt_dlp.cookies import CookieLoadError
from yt_dlp.extractor.getcourseru import GetCourseRuIE, GetCourseRuPlayerIE
from yt_dlp.networking.exceptions import HTTPError
from yt_dlp.utils import ExtractorError, urlencode_postdata

from clipflow.domain.events import (
    RequestsDiscovered,
    SelectionRequired,
    StageChanged,
    WorkCancelled,
)
from clipflow.domain.models import ContentKind, JobState, Service
from clipflow.providers.access import open_downloader, SessionAuth
from clipflow.providers.base import DownloadResult, MediaFailure, MediaItem, ProbeResult
from clipflow.providers.media import _QuietLogger


class SchoolAccessError(ExtractorError):
    def __init__(self, code):
        self.code = code
        super().__init__(code, expected=True)


class _Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.parts = {'title': [], 'description': []}
        self.players = []
        self.login_id = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get('class', '').split()
        role = next(
            (
                key
                for key in self.parts
                if any(value in classes for value in ('lesson-' + key, 'lesson-' + key + '-value'))
            ),
            None,
        )
        self.stack.append((tag, role or (self.stack[-1][1] if self.stack else None)))
        if tag == 'iframe' and attrs.get('src'):
            self.players.append((attrs['src'], attrs.get('title', '')))
        if tag == 'form' and 'state-login' in classes:
            self.login_id = attrs.get('data-xdget-id')
        if tag in {'br', 'hr', 'img', 'input', 'meta', 'link'}:
            self.stack.pop()

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        if self.stack and self.stack[-1][1]:
            self.parts[self.stack[-1][1]].append(data)

    def full_title(self, fallback):
        title = ' '.join(''.join(self.parts['title']).split()) or fallback or 'Урок GetCourse'
        description = ' '.join(''.join(self.parts['description']).split())
        return (
            f'{title} - {description}'
            if description and description.casefold() not in title.casefold()
            else title
        )


class PlayerExtractor(GetCourseRuPlayerIE):
    _VALID_URL = r'https?://(?:player02\.getcourse\.ru|[a-zA-Z0-9-]+\.(?:vhcdn|gceuproxy)\.com)/sign-player/?\?(?:[^#]+&)?json=[^#&]+'

    @classmethod
    def ie_key(cls):
        return GetCourseRuPlayerIE.ie_key()

    def _real_extract(self, url):
        info = super()._real_extract(url)
        info['getcourse_video_hash'] = info.get('title')
        info['title'] = 'Видео GetCourse'
        info['http_headers'] = {'Referer': url}
        return info


def _player_id(url):
    try:
        raw = parse_qs(urlparse(url).query)['json'][0].replace(' ', '+')
        value = json.loads(base64.urlsafe_b64decode(raw + '=' * (-len(raw) % 4)))
        identity = value.get('video_hash') or value.get('videoHash') or value.get('gcFileId')
        identity = str(identity or '')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', identity):
            raise ValueError
        return identity
    except (KeyError, ValueError, TypeError, AttributeError):
        raise SchoolAccessError('getcourse_invalid_player') from None


class LessonExtractor(GetCourseRuIE):
    @classmethod
    def ie_key(cls):
        return GetCourseRuIE.ie_key()

    def _login(self, hostname, username, password):
        url = f'https://{hostname}{self._LOGIN_URL_PATH}'
        page = self._download_webpage(url, None)
        parsed = _Page()
        parsed.feed(page)
        if not parsed.login_id:
            raise SchoolAccessError('getcourse_school_login_required')
        payload = {
            'action': 'processXdget',
            'xdgetId': parsed.login_id,
            'params[action]': 'login',
            'params[url]': url,
            'params[object_type]': 'cms_page',
            'params[object_id]': -1,
            'params[email]': username,
            'params[password]': password,
            'requestTime': self._search_regex(
                r'window\.requestTime\s*=\s*[\'"]?(\d+)', page, 'request time'
            ),
            'requestSimpleSign': self._search_regex(
                r'window\.requestSimpleSign\s*=\s*[\'"]([\da-f]+)', page, 'simple sign'
            ),
        }
        response = self._download_json(
            url,
            None,
            'Logging in to GetCourse school',
            data=urlencode_postdata(payload),
            headers={
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'Origin': f'https://{hostname}',
                'Referer': url,
                'X-Requested-With': 'XMLHttpRequest',
            },
        )
        if not isinstance(response, dict):
            raise SchoolAccessError('getcourse_school_login_required')
        result = response.get('data') if isinstance(response.get('data'), dict) else response
        if (
            result.get('errorMessage')
            or result.get('success') is False
            or response.get('success') is False
        ):
            raise SchoolAccessError('getcourse_school_login_required')

    def _real_extract(self, url):
        hostname = urlparse(url).hostname
        username, password = self._get_login_info(netrc_machine=hostname)
        if username:
            self._login(hostname, username, password)
        identity = self._match_id(url)
        webpage, handle = self._download_webpage_handle(url, identity)
        if self._LOGIN_URL_PATH in urlparse(handle.url).path:
            raise SchoolAccessError('getcourse_school_login_required')
        parsed = _Page()
        parsed.feed(webpage)
        title = parsed.full_title(
            self._og_search_title(webpage, default=None) or self._html_extract_title(webpage)
        )
        entries = []
        seen = set()
        for value, label in parsed.players:
            player = urljoin(url, value)
            if not PlayerExtractor.suitable(player):
                continue
            media_id = _player_id(player)
            if media_id in seen:
                continue
            seen.add(media_id)
            entries.append(
                {
                    '_type': 'url',
                    'ie_key': PlayerExtractor.ie_key(),
                    'id': media_id,
                    'url': player,
                    'title': f'{title} - {label}' if label else title,
                }
            )
        if not entries:
            raise SchoolAccessError('getcourse_no_media')
        if len(entries) > 1:
            for index, entry in enumerate(entries, 1):
                entry['title'] = f'{index:02d} - {entry["title"]}'
        return self.playlist_result(entries, identity, title)


class GetCourseProvider:
    def __init__(self, pipeline):
        self.pipeline = pipeline

    @contextmanager
    def _session(self, request, context):
        context.cancel.raise_if_cancelled()
        if request.link.service != Service.GETCOURSE or request.link.kind not in {
            ContentKind.LESSON,
            ContentKind.PLAYER,
        }:
            raise MediaFailure('invalid_request')
        try:
            access = dict(
                context.auth.options_for(request.options.auth_profile, request.link.canonical_url)
            )
            options = dict(
                access,
                quiet=True,
                no_warnings=True,
                logger=_QuietLogger(),
                skip_download=True,
                socket_timeout=30,
                retries=3,
            )
            if self.pipeline.node:
                options['js_runtimes'] = {'node': {'path': self.pipeline.node}}
            if self.pipeline.ffmpeg:
                options['ffmpeg_location'] = self.pipeline.ffmpeg
            with open_downloader(options, context=context) as ydl:
                ydl.add_info_extractor(LessonExtractor())
                ydl.add_info_extractor(PlayerExtractor())
                yield ydl, access
        except (WorkCancelled, MediaFailure):
            raise
        except Exception as error:
            context.cancel.raise_if_cancelled()
            seen = set()
            pending = [error]
            while pending:
                current = pending.pop()
                if current is None or id(current) in seen:
                    continue
                seen.add(id(current))
                if isinstance(current, SchoolAccessError):
                    raise MediaFailure(current.code) from None
                if isinstance(current, HTTPError) and current.status in {401, 403}:
                    raise MediaFailure('getcourse_access_denied') from None
                if isinstance(current, (LoadError, CookieLoadError, FileNotFoundError)):
                    raise MediaFailure('getcourse_auth_failed') from None
                nested = getattr(current, 'exc_info', None)
                pending.extend(
                    [nested[1] if nested else None, current.__cause__, current.__context__]
                )
            raise MediaFailure('getcourse_probe_failed') from None

    def _inspect(self, ydl, request, context):
        context.emit(StageChanged(JobState.PROBING))
        context.cancel.raise_if_cancelled()
        info = ydl.extract_info(request.link.canonical_url, download=False, process=False)
        context.cancel.raise_if_cancelled()
        entries = (
            info.get('entries')
            if isinstance(info, dict) and info.get('_type') == 'playlist'
            else [info]
        )
        items = []
        for index, entry in enumerate(entries or (), 1):
            context.cancel.raise_if_cancelled()
            if not isinstance(entry, dict) or not entry.get('id'):
                continue
            if request.link.kind == ContentKind.LESSON and isinstance(info, dict):
                entry = dict(entry, getcourse_lesson_id=info.get('id'))
            items.append(
                MediaItem(
                    str(entry['id']), index, 'video', entry.get('title') or 'Видео GetCourse', entry
                )
            )
        if not items:
            raise MediaFailure('getcourse_no_media')
        ids = {item.id for item in items}
        if request.selection is not None:
            if not request.selection or not set(request.selection).issubset(ids):
                raise MediaFailure('getcourse_selection_changed')
            items = [item for item in items if item.id in request.selection]
        return tuple(items)

    @staticmethod
    def _resolve(ydl, item, context):
        if item.info.get('_type') in {'url', 'url_transparent'}:
            context.cancel.raise_if_cancelled()
            info = ydl.extract_info(item.info['url'], download=False, process=False)
            context.cancel.raise_if_cancelled()
            if not isinstance(info, dict) or not (info.get('formats') or info.get('url')):
                raise MediaFailure('getcourse_no_media')
            if item.id not in {
                str(info.get('id') or ''),
                str(info.get('getcourse_video_hash') or ''),
            }:
                raise MediaFailure('getcourse_selection_changed')
            return replace(
                item,
                info=dict(
                    info,
                    id=item.id,
                    title=item.title,
                    getcourse_lesson_id=item.info.get('getcourse_lesson_id'),
                ),
            )
        return item

    def probe(self, request, context):
        with self._session(request, context) as (ydl, access):
            items = self._inspect(ydl, request, context)
            required = len(items) > 1 and request.selection is None
            if len(items) == 1:
                items = (self._resolve(ydl, items[0], context),)
            heights = {
                fmt['height']
                for item in items
                for fmt in item.info.get('formats') or ()
                if type(fmt.get('height')) is int
                and fmt['height'] > 0
                and fmt.get('vcodec') != 'none'
            }
            return ProbeResult(
                items,
                tuple(sorted(heights, reverse=True)) if request.options.format != 'mp3' else (),
                required,
            )

    def execute(self, request, context):
        with self._session(request, context) as (ydl, access):
            items = self._inspect(ydl, request, context)
            if len(items) > 1:
                if request.selection is None:
                    context.emit(
                        SelectionRequired(
                            tuple(item.id for item in items), tuple(item.title for item in items)
                        )
                    )
                    context.cancel.raise_if_cancelled()
                    return DownloadResult(())
                for offset in range(0, len(items), 25):
                    context.cancel.raise_if_cancelled()
                    context.emit(
                        RequestsDiscovered(
                            tuple(
                                replace(request, selection=(item.id,), label=item.title[:1000])
                                for item in items[offset : offset + 25]
                            )
                        )
                    )
                context.cancel.raise_if_cancelled()
                return DownloadResult((), len(items))
            item = self._resolve(ydl, items[0], context)
            session_context = replace(context, auth=SessionAuth(access, ydl.cookiejar))
            return DownloadResult(self.pipeline.save(item, request, session_context))
