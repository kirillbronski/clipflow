"""FFprobe checks and FFmpeg conversion of downloaded sources into the chosen format."""

import json
import os

from clipflow.domain.models import MediaItem
from clipflow.providers.base import MediaFailure
from clipflow.providers.processes import run_process
from clipflow.providers.publishing import publish


class MediaTools:
    def __init__(self, ffmpeg: str | None, ffprobe: str | None):
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe

    def probe(self, path, context):
        if not self.ffprobe:
            raise MediaFailure('tool_missing')
        try:
            data = run_process(
                [
                    self.ffprobe,
                    '-v',
                    'error',
                    '-show_streams',
                    '-show_format',
                    '-of',
                    'json',
                    str(path),
                ],
                context,
                capture=True,
            )
            return json.loads(data)
        except (ValueError, TypeError):
            raise MediaFailure('invalid_media') from None

    def verify(self, path, item, request, context):
        if not path.is_file() or path.stat().st_size == 0:
            raise MediaFailure('invalid_media')
        if item.kind == 'photo':
            return
        data = self.probe(path, context)
        streams = data.get('streams', [])
        kinds = {s.get('codec_type') for s in streams}
        fmt = request.options.format
        expected = {'mp4': 'mp4', 'mkv': 'matroska', 'webm': 'webm', 'mp3': 'mp3'}[fmt]
        if expected not in data.get('format', {}).get('format_name', ''):
            raise MediaFailure('invalid_media')
        if 'audio' not in kinds if fmt == 'mp3' else 'video' not in kinds:
            raise MediaFailure('invalid_media')

    def convert(self, source, target, request, context, work=None, tag=None):
        if not self.ffmpeg:
            raise MediaFailure('tool_missing')
        fmt = request.options.format
        codecs = {s.get('codec_name') for s in self.probe(source, context).get('streams', [])}
        args = [self.ffmpeg, '-v', 'error', '-nostdin', '-y', '-i', str(source)]
        if fmt == 'mp3':
            args += ['-vn', '-c:a', 'libmp3lame', '-b:a', '320k']
        elif fmt == 'webm' and not codecs.issubset({'vp8', 'vp9', 'av1', 'opus', 'vorbis'}):
            args += [
                '-map',
                '0:v:0',
                '-map',
                '0:a:0?',
                '-c:v',
                'libvpx-vp9',
                '-crf',
                '32',
                '-b:v',
                '0',
                '-c:a',
                'libopus',
            ]
        else:
            args += ['-map', '0:v:0', '-map', '0:a:0?', '-c', 'copy']
        if tag:
            args += ['-metadata', 'comment=' + tag]
        work = work or target
        temporary = work.with_name(work.stem + '.processing' + target.suffix)
        run_process(args + [str(temporary)], context)
        self.verify(temporary, MediaItem('', 1, 'video', '', {}), request, context)
        context.cancel.raise_if_cancelled()
        if tag:
            return publish(temporary, target)
        os.replace(temporary, target)
        return target
