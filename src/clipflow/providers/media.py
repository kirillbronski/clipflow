"""Common resumable transfer, verified conversion and atomic sidecar publishing."""

import copy
import os
import shutil
import time
from pathlib import Path
from urllib.parse import urlsplit

from yt_dlp.networking import Request
from yt_dlp.networking.exceptions import HTTPError

from clipflow.domain.events import (
    FilesSaved,
    ProgressChanged,
    StageChanged,
    TitleChanged,
    WorkCancelled,
)
from clipflow.domain.models import DownloadRequest, JobState, Service
from clipflow.domain.paths import UnsafePath
from clipflow.providers.access import open_downloader
from clipflow.providers.base import ExecutionContext, MediaFailure, MediaItem
from clipflow.providers.conversion import MediaTools
from clipflow.providers.media_plan import plan_media
from clipflow.providers.processes import run_process
from clipflow.providers.publishing import find_tagged, write_caption


class _QuietLogger:
    def debug(self, message):
        pass

    def warning(self, message):
        pass

    def error(self, message):
        pass


class MediaPipeline:
    def __init__(
        self, *, ffmpeg: str | None = None, ffprobe: str | None = None, node: str | None = None
    ):
        self.ffmpeg = ffmpeg or shutil.which('ffmpeg')
        self.ffprobe = ffprobe or shutil.which('ffprobe')
        self.node = node or shutil.which('node')

    @property
    def _tools(self) -> MediaTools:
        return MediaTools(self.ffmpeg, self.ffprobe)

    # Self-test and tests drive the process runner and FFprobe through the pipeline.
    _run = staticmethod(run_process)

    def _probe(self, path, context):
        return self._tools.probe(path, context)

    def save(
        self, item: MediaItem, request: DownloadRequest, context: ExecutionContext
    ) -> tuple[Path, ...]:
        context.cancel.raise_if_cancelled()
        try:
            return self._save(item, request, context)
        except (WorkCancelled, MediaFailure):
            raise
        except UnsafePath:
            raise MediaFailure('invalid_path') from None
        except OSError:
            context.cancel.raise_if_cancelled()
            raise MediaFailure('write_failed') from None
        except Exception:  # noqa: BLE001  # сторонняя библиотека: наружу только безопасный код, без секретов
            context.cancel.raise_if_cancelled()
            raise MediaFailure('download_failed') from None

    def _save(self, item, request, context):
        plan = plan_media(request, item)
        plan.target.parent.mkdir(parents=True, exist_ok=True)
        tools = self._tools
        if plan.tag:
            existing = find_tagged(plan.target, plan.tag, context, tools.probe)
        else:
            existing = plan.target if plan.target.exists() else None
        # YouTube rows show the file name they will get; other services keep their media title.
        planned = (existing or plan.target).stem if plan.tag else item.title
        context.emit(TitleChanged(planned))
        if existing is not None:
            tools.verify(existing, item, request, context)
            target = existing
        else:
            target = self._download(item, request, context, plan, planned)
        context.cancel.raise_if_cancelled()
        files = (target, *self._captions(item, request, target))
        context.cancel.raise_if_cancelled()
        Path(str(plan.work) + '.ytdl').unlink(missing_ok=True)
        context.emit(FilesSaved(files))
        return files

    def _download(self, item, request, context, plan, planned):
        url = str(item.info.get('url') or '')
        if item.kind == 'photo' and urlsplit(url).scheme not in {'http', 'https'}:
            raise MediaFailure('invalid_media')
        context.emit(StageChanged(JobState.DOWNLOADING))
        instagram = request.link.service == Service.INSTAGRAM
        with open_downloader(
            self._options(item, request, context, plan.work),
            context=context,
            instagram_context=context if instagram else None,
            instagram_kind='cdn',
        ) as ydl:
            if item.kind == 'photo':
                self._photo(ydl, url, plan.target, context, item.info.get('http_headers'))
                return plan.target
            return self._download_video(ydl, item, request, context, plan, planned)

    def _download_video(self, ydl, item, request, context, plan, planned):
        info = copy.deepcopy(dict(item.info))
        info.update(id=item.id, title=item.title)
        # Probe metadata keeps yt-dlp's default selection; reusing it for another format
        # gives HTTP403.
        info.pop('requested_formats', None)
        info.pop('requested_downloads', None)
        if not info.get('url') and not info.get('formats'):
            raise MediaFailure('invalid_media')
        result = ydl.process_ie_result(info, download=True)
        source = self._source_file(result, ydl, plan.target.parent)
        context.cancel.raise_if_cancelled()
        context.emit(StageChanged(JobState.PROCESSING))
        tools = self._tools
        target = tools.convert(source, plan.target, request, context, plan.work, plan.tag)
        tools.verify(target, item, request, context)
        if plan.tag and target.stem != planned:
            context.emit(TitleChanged(target.stem))  # a name collision added " (n)"
        source.unlink(missing_ok=True)
        Path(str(source) + '.ytdl').unlink(missing_ok=True)
        return target

    @staticmethod
    def _captions(item, request, target):
        description = item.info.get('description')
        if request.options.description and isinstance(description, str) and description.strip():
            return (write_caption(target, description, request.options.description),)
        return ()

    def _options(self, item, request, context, target):
        options = dict(
            context.auth.options_for(request.options.auth_profile, request.link.canonical_url)
        )
        limit = f'[height<={request.options.max_height}]' if request.options.max_height else ''
        template = str(target.parent / (target.stem + '.source.')).replace('%', '%%') + '%(ext)s'
        options.update(
            outtmpl=template,
            noplaylist=True,
            windowsfilenames=True,
            quiet=True,
            no_warnings=True,
            logger=_QuietLogger(),
            continuedl=True,
            overwrites=False,
            retries=0 if request.link.service == Service.INSTAGRAM else 3,
            socket_timeout=30,
            concurrent_fragment_downloads=1 if request.link.service == Service.INSTAGRAM else 8,
            progress_hooks=[self._telemetry(context)],
            postprocessors=[],
            format='bestaudio/best'
            if request.options.format == 'mp3'
            else f'bestvideo{limit}+bestaudio/best{limit}',
            merge_output_format='mkv',
        )
        if request.link.service == Service.INSTAGRAM:
            options.update(extractor_retries=0, fragment_retries=0, hls_prefer_native=True)
        if self.ffmpeg:
            options['ffmpeg_location'] = self.ffmpeg
        if self.node:
            options['js_runtimes'] = {'node': {'path': self.node}}
        return options

    @staticmethod
    def _telemetry(context):
        last = -float('inf')
        sample_time = None
        sample_bytes = 0
        observed = 0
        total = None
        stream = None

        def hook(data):
            nonlocal last, sample_time, sample_bytes, observed, total, stream
            context.cancel.raise_if_cancelled()
            now = time.monotonic()
            downloaded = data.get('downloaded_bytes')
            if downloaded is None:
                downloaded = observed if data.get('status') == 'finished' else 0
            identity = data.get('filename')
            if (
                sample_time is None
                or downloaded < observed
                or (identity is not None and identity != stream)
            ):
                sample_time = now
                sample_bytes = downloaded
                total = None
            if identity is not None:
                stream = identity
            observed = downloaded
            total = data.get('total_bytes') or data.get('total_bytes_estimate') or total
            if data.get('status') == 'finished' or now - last >= 0.5:
                last = now
                elapsed = now - sample_time
                speed = max(0, (observed - sample_bytes) / elapsed) if elapsed > 0 else None
                eta = (
                    max(0, (total - observed) / speed)
                    if total and speed and total >= observed
                    else None
                )
                context.emit(ProgressChanged(observed, total, speed, eta))
                sample_time = now
                sample_bytes = observed
            context.cancel.raise_if_cancelled()

        return hook

    def _photo(self, ydl, url, target, context, source_headers=None):
        partial = Path(str(target) + '.part')
        offset = partial.stat().st_size if partial.exists() else 0
        headers = dict(source_headers or {})
        if offset:
            headers['Range'] = f'bytes={offset}-'
        hook = self._telemetry(context)
        try:
            response = ydl.urlopen(Request(url, headers=headers))
        except HTTPError as error:
            try:
                complete = (
                    offset > 0
                    and error.status == 416
                    and error.response.headers.get('Content-Range') == f'bytes */{offset}'
                )
            finally:
                error.close()
            if not complete:
                raise
            context.cancel.raise_if_cancelled()
            os.replace(partial, target)
            return
        with response:
            if offset and (
                response.status != 206
                or not response.headers.get('Content-Range', '').startswith(f'bytes {offset}-')
            ):
                offset = 0  # Range is optional; a full response must replace, never append.
            length = int(response.headers.get('Content-Length') or 0)
            total = offset + length if length else None
            downloaded = offset
            start = time.monotonic()
            with partial.open('ab' if offset else 'wb') as output:
                while True:
                    context.cancel.raise_if_cancelled()
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    output.write(chunk)
                    downloaded += len(chunk)
                    hook(
                        {
                            'downloaded_bytes': downloaded,
                            'total_bytes': total,
                            'speed': (downloaded - offset) / max(0.01, time.monotonic() - start),
                        }
                    )
            context.cancel.raise_if_cancelled()
            if not downloaded or (total is not None and downloaded != total):
                raise MediaFailure('incomplete_download')
        os.replace(partial, target)

    @staticmethod
    def _source_file(result, ydl, directory):
        candidates = [result.get('filepath'), result.get('_filename'), ydl.prepare_filename(result)]
        candidates += [d.get('filepath') for d in result.get('requested_downloads') or ()]
        for value in candidates:
            if value:
                path = Path(value).resolve()
                if path.is_relative_to(directory.resolve()) and path.is_file():
                    return path
        raise MediaFailure('missing_output')
