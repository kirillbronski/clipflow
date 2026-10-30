"""YouTube/Music metadata and playlist discovery; transfers use the shared pipeline."""

import re
from dataclasses import replace

from clipflow.domain.events import RequestsDiscovered, StageChanged, TitleChanged, WorkCancelled
from clipflow.domain.models import ContentKind, DownloadRequest, JobState, PlaylistPosition, Service
from clipflow.domain.paths import UnsafePath, output_path
from clipflow.domain.urls import parse_url
from clipflow.providers.access import open_downloader
from clipflow.providers.base import (
    DownloadResult,
    ExecutionContext,
    MediaFailure,
    MediaItem,
    ProbeResult,
)
from clipflow.providers.media import MediaPipeline, _QuietLogger


class YouTubeProvider:
    def __init__(self, pipeline: MediaPipeline):
        self.pipeline = pipeline

    def probe(self, request: DownloadRequest, context: ExecutionContext) -> ProbeResult:
        context.cancel.raise_if_cancelled()
        if (
            request.link.service != Service.YOUTUBE
            or request.link.kind not in {ContentKind.VIDEO, ContentKind.PLAYLIST}
            or not self._valid_id(request.link.canonical_id)
        ):
            raise MediaFailure('invalid_request')
        context.emit(StageChanged(JobState.PROBING))
        context.cancel.raise_if_cancelled()
        info = self._extract(request, context)
        if not info:
            raise MediaFailure('unavailable_media')
        if request.link.kind == ContentKind.PLAYLIST:
            items = []
            for ordinal, entry in enumerate(info.get('entries') or (), 1):
                context.cancel.raise_if_cancelled()
                if not isinstance(entry, dict) or not self._valid_id(entry.get('id')):
                    continue
                identity = entry['id']
                if request.selection is not None and identity not in request.selection:
                    continue
                index = entry.get('playlist_index')
                if type(index) is not int or index < 1:
                    index = ordinal
                items.append(MediaItem(identity, index, 'video', self._title(entry), entry))
            if not items:
                raise MediaFailure('unavailable_media')
            title = info.get('title')
            title = (
                ' '.join(title.split())[:500] if isinstance(title, str) and title.strip() else None
            )
            return ProbeResult(tuple(items), (), collection_title=title)
        identity = info.get('id') or request.link.canonical_id
        if (
            not self._valid_id(identity)
            or info.get('_type') in {'playlist', 'url', 'url_transparent'}
            or not (info.get('url') or info.get('formats'))
        ):
            raise MediaFailure('unavailable_media')
        if request.selection is not None and identity not in request.selection:
            raise MediaFailure('unavailable_media')
        index = request.playlist.index if request.playlist else 1
        item = MediaItem(identity, index, 'video', self._title(info), info)
        heights = {
            f['height']
            for f in info.get('formats') or ()
            if isinstance(f, dict)
            and type(f.get('height')) is int
            and f['height'] > 0
            and f.get('vcodec') != 'none'
        }
        if type(info.get('height')) is int and info['height'] > 0:
            heights.add(info['height'])
        return ProbeResult(
            (item,), tuple(sorted(heights, reverse=True)) if request.options.format != 'mp3' else ()
        )

    def planned_title(self, request: DownloadRequest, context: ExecutionContext) -> str:
        """The file name this single video will get, from one metadata request."""
        if request.link.kind != ContentKind.VIDEO:
            raise MediaFailure('invalid_request')
        item = self.probe(request, context).items[0]
        try:
            return output_path(request, item, None, None).stem
        except UnsafePath:
            return item.title

    def execute(self, request: DownloadRequest, context: ExecutionContext) -> DownloadResult:
        result = self.probe(request, context)
        if request.link.kind != ContentKind.PLAYLIST:
            return DownloadResult(self.pipeline.save(result.items[0], request, context))
        if result.collection_title:
            context.emit(TitleChanged(result.collection_title))
        pending = []
        count = 0
        for item in result.items:
            context.cancel.raise_if_cancelled()
            # Persist only canonical identities/options, never raw CDN URLs or credentials.
            origin = 'music.youtube.com' if request.link.is_music else 'www.youtube.com'
            child = replace(
                request,
                link=parse_url(f'https://{origin}/watch?v={item.id}'),
                selection=None,
                playlist=PlaylistPosition(
                    request.link.canonical_id, item.index, result.collection_title
                ),
                label=item.title[:1000],
            )
            pending.append(child)
            count += 1
            if len(pending) == 25:
                context.emit(RequestsDiscovered(tuple(pending)))
                pending.clear()
        context.cancel.raise_if_cancelled()
        if pending:
            context.emit(RequestsDiscovered(tuple(pending)))
        context.cancel.raise_if_cancelled()
        return DownloadResult((), count)

    @staticmethod
    def _valid_id(value):
        return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,100}', value) is not None

    @staticmethod
    def _title(info):
        title = info.get('title')
        return title if isinstance(title, str) and title.strip() else 'YouTube video'

    def _extract(self, request, context):
        try:
            options = dict(
                context.auth.options_for(request.options.auth_profile, request.link.canonical_url)
            )

            def check_cancel(info, *, incomplete=False):
                context.cancel.raise_if_cancelled()
                return None

            options.update(
                quiet=True,
                no_warnings=True,
                logger=_QuietLogger(),
                skip_download=True,
                noplaylist=request.link.kind != ContentKind.PLAYLIST,
                extract_flat='in_playlist',
                lazy_playlist=True,
                ignoreerrors=request.link.kind == ContentKind.PLAYLIST,
                socket_timeout=30,
                retries=3,
                match_filter=check_cancel,
            )
            if self.pipeline.node:
                options['js_runtimes'] = {'node': {'path': self.pipeline.node}}
            if self.pipeline.ffmpeg:
                options['ffmpeg_location'] = self.pipeline.ffmpeg
            with open_downloader(options, context=context) as ydl:
                info = ydl.extract_info(request.link.canonical_url, download=False)
                if isinstance(info, dict) and request.link.kind == ContentKind.PLAYLIST:
                    # yt-dlp pages can be lazy and perform requests during iteration.
                    # Consume within its lifetime and the safe exception boundary.
                    entries = []
                    for entry in info.get('entries') or ():
                        context.cancel.raise_if_cancelled()
                        entries.append(entry)
                    info = dict(info, entries=tuple(entries))
            context.cancel.raise_if_cancelled()
            return info if isinstance(info, dict) else None
        except (WorkCancelled, MediaFailure):
            raise
        except Exception:
            context.cancel.raise_if_cancelled()
            raise MediaFailure('probe_failed') from None
