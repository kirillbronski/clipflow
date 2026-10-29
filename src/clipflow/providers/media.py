"""Common resumable transfer, verified conversion and atomic sidecar publishing."""
import copy
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
from tempfile import NamedTemporaryFile
import time
from urllib.parse import urlsplit

from yt_dlp import YoutubeDL
from yt_dlp.networking import Request
from yt_dlp.networking.exceptions import HTTPError

from clipflow.domain.events import FilesSaved, ProgressChanged, StageChanged, WorkCancelled,TitleChanged
from clipflow.domain.models import DownloadRequest, JobState, Service
from clipflow.domain.paths import PostIdentity, UnsafePath, output_path
from clipflow.providers.base import ExecutionContext, MediaFailure, MediaItem
from clipflow.providers.access import open_downloader


class _QuietLogger:
    def debug(self, message): pass
    def warning(self, message): pass
    def error(self, message): pass


class MediaPipeline:
    def __init__(self, *, ffmpeg: str | None = None, ffprobe: str | None = None,
                 node: str | None = None):
        self.ffmpeg = ffmpeg or shutil.which('ffmpeg')
        self.ffprobe = ffprobe or shutil.which('ffprobe')
        self.node = node or shutil.which('node')

    def save(self, item: MediaItem, request: DownloadRequest,
             context: ExecutionContext) -> tuple[Path, ...]:
        context.cancel.raise_if_cancelled()
        context.emit(TitleChanged(item.title))
        try:
            post = None
            if request.link.service == Service.INSTAGRAM:
                code = item.info.get('post_code') or request.link.canonical_id
                published = item.info.get('published_at')
                post = PostIdentity(str(code), item.info.get('post_title'),
                                    published if isinstance(published, datetime) else None)
            target = output_path(request, item, item.info.get('author'), post)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                self._verify(target, item, request, context)
            else:
                url = str(item.info.get('url') or '')
                if item.kind == 'photo' and urlsplit(url).scheme not in {'http', 'https'}:
                    raise MediaFailure('invalid_media')
                context.emit(StageChanged(JobState.DOWNLOADING))
                with open_downloader(self._options(item, request, context, target),
                                     context=context,
                                     instagram_context=context if request.link.service == Service.INSTAGRAM else None,
                                     instagram_kind='cdn') as ydl:
                    if item.kind == 'photo':
                        self._photo(ydl, url, target, context, item.info.get('http_headers'))
                    else:
                        info = copy.deepcopy(dict(item.info))
                        info.update(id=item.id, title=item.title)
                        if not info.get('url') and not info.get('formats'):
                            raise MediaFailure('invalid_media')
                        result = ydl.process_ie_result(info, download=True)
                        source = self._source_file(result, ydl, target.parent)
                        context.cancel.raise_if_cancelled()
                        context.emit(StageChanged(JobState.PROCESSING))
                        self._convert(source, target, request, context)
                        self._verify(target, item, request, context)
                        source.unlink(missing_ok=True)
                        Path(str(source)+'.ytdl').unlink(missing_ok=True)
            context.cancel.raise_if_cancelled()
            files = (target,)
            description = item.info.get('description')
            if request.options.description and isinstance(description, str) and description.strip():
                files += (self._caption(target, description, request.options.description),)
            context.cancel.raise_if_cancelled()
            Path(str(target)+'.ytdl').unlink(missing_ok=True)
            context.emit(FilesSaved(files))
            return files
        except (WorkCancelled, MediaFailure):
            raise
        except UnsafePath:
            raise MediaFailure('invalid_path') from None
        except OSError:
            context.cancel.raise_if_cancelled()
            raise MediaFailure('write_failed') from None
        except Exception:
            context.cancel.raise_if_cancelled()
            raise MediaFailure('download_failed') from None

    def _options(self, item, request, context, target):
        options = dict(context.auth.options_for(request.options.auth_profile, request.link.canonical_url))
        limit = f'[height<={request.options.max_height}]' if request.options.max_height else ''
        template = str(target.parent/(target.stem+'.source.')).replace('%', '%%')+'%(ext)s'
        options.update(outtmpl=template, noplaylist=True, windowsfilenames=True,
                       quiet=True, no_warnings=True, logger=_QuietLogger(),
                       continuedl=True, overwrites=False, retries=0 if request.link.service == Service.INSTAGRAM else 3, socket_timeout=30,
                       concurrent_fragment_downloads=1 if request.link.service == Service.INSTAGRAM else 8,
                       progress_hooks=[self._telemetry(context)], postprocessors=[],
                       format='bestaudio/best' if request.options.format == 'mp3' else f'bestvideo{limit}+bestaudio/best{limit}',
                       merge_output_format='mkv')
        if request.link.service == Service.INSTAGRAM:
            options.update(extractor_retries=0,fragment_retries=0,hls_prefer_native=True)
        if self.ffmpeg:
            options['ffmpeg_location'] = self.ffmpeg
        if self.node:
            options['js_runtimes'] = {'node': {'path': self.node}}
        return options

    @staticmethod
    def _telemetry(context):
        last = -float('inf')
        def hook(data):
            nonlocal last
            context.cancel.raise_if_cancelled()
            now = time.monotonic()
            if data.get('status') == 'finished' or now-last >= .5:
                last = now
                total = data.get('total_bytes') or data.get('total_bytes_estimate')
                context.emit(ProgressChanged(data.get('downloaded_bytes') or 0, total,
                                             data.get('speed'), data.get('eta')))
            context.cancel.raise_if_cancelled()
        return hook

    def _photo(self, ydl, url, target, context, source_headers=None):
        partial = Path(str(target)+'.part')
        offset = partial.stat().st_size if partial.exists() else 0
        headers = dict(source_headers or {})
        if offset:
            headers['Range'] = f'bytes={offset}-'
        hook = self._telemetry(context)
        try:
            response = ydl.urlopen(Request(url, headers=headers))
        except HTTPError as error:
            try:
                complete = offset > 0 and error.status == 416 and error.response.headers.get('Content-Range') == f'bytes */{offset}'
            finally:
                error.close()
            if not complete:
                raise
            context.cancel.raise_if_cancelled()
            os.replace(partial, target)
            return
        with response:
            if offset and (response.status != 206 or not response.headers.get('Content-Range', '').startswith(f'bytes {offset}-')):
                offset = 0  # Range is optional; a full response must replace, never append.
            length = int(response.headers.get('Content-Length') or 0)
            total = offset+length if length else None
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
                    hook({'downloaded_bytes': downloaded, 'total_bytes': total,
                          'speed': (downloaded-offset)/max(.01, time.monotonic()-start)})
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

    @staticmethod
    def _run(args, context, *, capture=False, capture_error=False, expected_retcodes=(0,)):
        context.cancel.raise_if_cancelled()
        try:
            with subprocess.Popen(args, stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                                  stderr=subprocess.PIPE if capture_error else subprocess.DEVNULL,
                                  start_new_session=os.name!='nt',
                                  creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0) as process:
                try:
                    while True:
                        try:
                            output, errors = process.communicate(timeout=.1)
                            break
                        except subprocess.TimeoutExpired:
                            context.cancel.raise_if_cancelled()
                    context.cancel.raise_if_cancelled()
                    if process.returncode not in expected_retcodes:
                        raise MediaFailure('processing_failed')
                    return errors if capture_error else output
                except BaseException:
                    if process.poll() is None:
                        MediaPipeline._stop_process_tree(process)
                        try:
                            process.communicate(timeout=2)
                        except subprocess.TimeoutExpired:
                            MediaPipeline._stop_process_tree(process,force=True)
                            process.communicate(timeout=2)
                    raise
        except FileNotFoundError:
            raise MediaFailure('tool_missing') from None

    @staticmethod
    def _stop_process_tree(process,force=False):
        if os.name=='nt':
            # Chocolatey and user launchers can own the actual FFmpeg child.
            # Kill the tree while its root still exists, then drain inherited
            # pipes: killing just the shim can leave communicate() blocked.
            taskkill=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/taskkill.exe'
            try:
                subprocess.run([str(taskkill),'/PID',str(process.pid),'/T','/F'],
                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=2,
                    creationflags=subprocess.CREATE_NO_WINDOW)
            except (OSError,subprocess.TimeoutExpired): pass
            if process.poll() is None: process.kill()
        else:
            try: os.killpg(process.pid,signal.SIGKILL if force else signal.SIGTERM)
            except ProcessLookupError: pass

    def _probe(self, path, context):
        if not self.ffprobe:
            raise MediaFailure('tool_missing')
        try:
            data = self._run([self.ffprobe, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)], context, capture=True)
            return json.loads(data)
        except (ValueError, TypeError):
            raise MediaFailure('invalid_media') from None

    def _verify(self, path, item, request, context):
        if not path.is_file() or path.stat().st_size == 0:
            raise MediaFailure('invalid_media')
        if item.kind == 'photo':
            return
        data = self._probe(path, context)
        streams = data.get('streams', [])
        kinds = {s.get('codec_type') for s in streams}
        fmt = request.options.format
        expected = {'mp4': 'mp4', 'mkv': 'matroska', 'webm': 'webm', 'mp3': 'mp3'}[fmt]
        if expected not in data.get('format', {}).get('format_name', ''):
            raise MediaFailure('invalid_media')
        if ('audio' not in kinds if fmt == 'mp3' else 'video' not in kinds):
            raise MediaFailure('invalid_media')

    def _convert(self, source, target, request, context):
        if not self.ffmpeg:
            raise MediaFailure('tool_missing')
        fmt = request.options.format
        codecs = {s.get('codec_name') for s in self._probe(source, context).get('streams', [])}
        args = [self.ffmpeg, '-v', 'error', '-nostdin', '-y', '-i', str(source)]
        if fmt == 'mp3':
            args += ['-vn', '-c:a', 'libmp3lame', '-b:a', '192k']
        elif fmt == 'webm' and not codecs.issubset({'vp8', 'vp9', 'av1', 'opus', 'vorbis'}):
            args += ['-map', '0:v:0', '-map', '0:a:0?', '-c:v', 'libvpx-vp9', '-crf', '32', '-b:v', '0', '-c:a', 'libopus']
        else:
            args += ['-map', '0:v:0', '-map', '0:a:0?', '-c', 'copy']
        temporary = target.with_name(target.stem+'.processing'+target.suffix)
        self._run(args+[str(temporary)], context)
        self._verify(temporary, MediaItem('', 1, 'video', '', {}), request, context)
        context.cancel.raise_if_cancelled()
        os.replace(temporary, target)

    @staticmethod
    def _caption(target, description, fmt):
        caption = target.with_suffix('.'+fmt)
        temporary = None
        try:
            with NamedTemporaryFile(mode='w', encoding='utf-8-sig' if fmt == 'txt' else 'utf-8',
                                    newline='', dir=caption.parent, prefix=caption.name+'.',
                                    suffix='.tmp', delete=False) as output:
                temporary = Path(output.name)
                output.write(description)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, caption)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return caption
