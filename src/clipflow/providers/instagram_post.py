"""One Instagram post/Reel/carousel, never implicit profile discovery."""

import re
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from yt_dlp.extractor.instagram import InstagramIE
from yt_dlp.networking.exceptions import HTTPError

from clipflow.domain.events import StageChanged, WorkCancelled
from clipflow.domain.models import ContentKind, JobState, Service
from clipflow.providers.access import SessionAuth, open_downloader
from clipflow.providers.base import DownloadResult, MediaFailure, MediaItem, ProbeResult
from clipflow.providers.media import _QuietLogger


class InstagramExtractor(InstagramIE):
    @classmethod
    def ie_key(cls):
        return InstagramIE.ie_key()

    def _extract_product_media(self, media):
        info = super()._extract_product_media(media)
        if (
            not info.get('formats')
            and media.get('media_type') != 2
            and not media.get('video_versions')
            and not media.get('video_dash_manifest')
        ):
            candidates = [
                v
                for v in (media.get('image_versions2') or {}).get('candidates', [])
                if isinstance(v, dict)
                and isinstance(v.get('url'), str)
                and urlparse(v['url']).scheme in {'http', 'https'}
            ]
            if candidates:
                image = max(
                    candidates,
                    key=lambda v: (
                        self._dimension(v.get('width')) * self._dimension(v.get('height'))
                    ),
                )
                ext = Path(urlparse(image['url']).path).suffix.lower().lstrip('.')
                if ext not in {'jpg', 'jpeg', 'png', 'webp', 'avif'}:
                    ext = 'jpg'
                info.update(
                    _clipflow_photo=True,
                    url=image['url'],
                    ext=ext,
                    width=image.get('width'),
                    height=image.get('height'),
                )
                # InstagramIE rejects a single photo as "no video" without a format.
                info['formats'] = [
                    {'url': image['url'], 'ext': ext, 'vcodec': 'none', 'acodec': 'none'}
                ]
        return info

    @staticmethod
    def _dimension(value):
        return value if type(value) is int and value > 0 else 0


class InstagramMediaFailure(MediaFailure):
    """A safe per-item diagnostic, raised after preserving earlier FilesSaved."""

    def __init__(self, media_id, index, reason):
        super().__init__('instagram_item_failed')
        self.media_id = media_id
        self.index = index
        self.reason = reason
        self.args = (f'instagram_item_failed:{index:03d}:{reason}',)


def _network_reason(error, fallback):
    pending = [error]
    seen = set()
    while pending:
        current = pending.pop()
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, HTTPError):
            if current.status == 429:
                return 'instagram_rate_limited'
            if current.status in {401, 403}:
                return 'instagram_access_denied'
        nested = getattr(current, 'exc_info', None)
        pending.extend([nested[1] if nested else None, current.__cause__, current.__context__])
    return fallback


def _author(sources):
    for source in sources:
        for key in ('channel', 'uploader_id'):
            value = source.get(key)
            if (
                isinstance(value, str)
                and re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.]{0,29}', value)
                and not value.isdigit()
            ):
                return value
    return 'Unknown author'


def _published(sources):
    for source in sources:
        date = source.get('upload_date')
        if isinstance(date, str) and re.fullmatch(r'\d{8}', date):
            try:
                return datetime.strptime(date, '%Y%m%d').replace(tzinfo=UTC)
            except ValueError:
                pass
        stamp = source.get('timestamp')
        if type(stamp) in (int, float):
            try:
                return datetime.fromtimestamp(stamp, UTC)
            except (ValueError, OverflowError, OSError):
                pass
    return None


class InstagramPostProvider:
    def __init__(self, pipeline):
        self.pipeline = pipeline

    def probe(self, request, context):
        return self._probe(request, context)[0]

    def _probe(self, request, context):
        context.cancel.raise_if_cancelled()
        code = request.link.canonical_id
        if (
            request.link.service != Service.INSTAGRAM
            or request.link.kind != ContentKind.POST
            or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', code)
        ):
            raise MediaFailure('instagram_post_required')
        if context.instagram_rate is None:
            raise MediaFailure('instagram_rate_policy_required')
        context.emit(StageChanged(JobState.PROBING))
        context.cancel.raise_if_cancelled()
        try:
            access = dict(
                context.auth.options_for(request.options.auth_profile, request.link.canonical_url)
            )
            options = dict(access)
            options.update(
                quiet=True,
                no_warnings=True,
                logger=_QuietLogger(),
                skip_download=True,
                noplaylist=False,
                playlist_items=None,
                ignoreerrors=False,
                retries=0,
                extractor_retries=0,
                fragment_retries=0,
                socket_timeout=30,
                concurrent_fragment_downloads=1,
            )
            with open_downloader(options, instagram_context=context, instagram_kind='post') as ydl:
                ydl.add_info_extractor(InstagramExtractor())
                info = ydl.extract_info(request.link.canonical_url, download=False, process=False)
                context.cancel.raise_if_cancelled()
                return self._normalize(info, request, context), SessionAuth(access, ydl.cookiejar)
        except (WorkCancelled, MediaFailure):
            raise
        except Exception as error:
            context.cancel.raise_if_cancelled()
            raise MediaFailure(_network_reason(error, 'instagram_probe_failed')) from None

    def _normalize(self, info, request, context):
        if not isinstance(info, dict):
            raise MediaFailure('instagram_unavailable_media')
        entries = list(info.get('entries') or ()) if info.get('_type') == 'playlist' else [info]
        if not entries or not all(isinstance(v, dict) for v in entries):
            raise MediaFailure('instagram_incomplete_metadata')
        sources = [info, *entries]
        author = _author(sources)
        caption = next(
            (
                v['description']
                for v in sources
                if isinstance(v.get('description'), str) and v['description'].strip()
            ),
            None,
        )
        published = _published(sources)
        post_title = (
            ' '.join(caption.split()) if caption else 'Карусель' if len(entries) > 1 else 'Пост'
        )
        items = []
        for index, entry in enumerate(entries, 1):
            context.cancel.raise_if_cancelled()
            if entry.get('_type') in {'playlist', 'url', 'url_transparent'}:
                raise MediaFailure('instagram_invalid_metadata')
            is_photo = entry.get('_clipflow_photo') is True
            if not is_photo and not (entry.get('formats') or entry.get('url')):
                raise MediaFailure('instagram_unavailable_media')
            identity = entry.get('id')
            if not isinstance(identity, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', identity):
                identity = f'{request.link.canonical_id}_{index}'
            # Discard lazy comment callbacks/internal postprocessor objects before
            # handing raw metadata to the generic pipeline's immutable copy.
            raw = {k: v for k, v in entry.items() if not k.startswith('__') and k != 'comments'}
            headers = dict(raw.get('http_headers') or {})
            headers.setdefault('Referer', 'https://www.instagram.com/')
            raw.update(
                author=author,
                post_code=request.link.canonical_id,
                post_title=post_title,
                description=caption,
                published_at=published,
                http_headers=headers,
            )
            title = f'{author} - {" ".join(caption.split())}' if caption else author
            items.append(MediaItem(identity, index, 'photo' if is_photo else 'video', title, raw))
        if request.selection is not None:
            if not request.selection or not set(request.selection).issubset({v.id for v in items}):
                raise MediaFailure('instagram_selection_changed')
            items = [v for v in items if v.id in request.selection]
        items = [
            v
            for v in items
            if request.options.media_filter == 'all' or v.kind == request.options.media_filter
        ]
        if not items:
            raise MediaFailure('instagram_no_matching_media')
        heights = {
            fmt['height']
            for item in items
            if item.kind == 'video'
            for fmt in item.info.get('formats') or ()
            if isinstance(fmt, dict)
            and type(fmt.get('height')) is int
            and fmt['height'] > 0
            and fmt.get('vcodec') != 'none'
        }
        return ProbeResult(
            tuple(items),
            tuple(sorted(heights, reverse=True)) if request.options.format != 'mp3' else (),
        )

    def execute(self, request, context):
        result, auth = self._probe(request, context)
        context = replace(context, auth=auth)
        files = []
        for item in result.items:
            context.cancel.raise_if_cancelled()
            try:
                files.extend(self.pipeline.save(item, request, context))
            except MediaFailure as error:
                reason = _network_reason(error, error.code)
                raise InstagramMediaFailure(item.id, item.index, reason) from None
        context.cancel.raise_if_cancelled()
        context.instagram_rate.record_completed_post()
        store = getattr(context.instagram_rate, 'store', None)
        if store:
            store.mark_completed(
                str(result.items[0].info.get('author', '')).lower(), request.link.canonical_id
            )
        return DownloadResult(tuple(files))
