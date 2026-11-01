"""Media details from extractor info: only sane values survive, nothing here raises."""

import math
import re
from collections.abc import Mapping
from dataclasses import replace

from clipflow.domain.models import DownloadOptions, MediaDetails, Service, is_https

_AUTHOR_LIMIT = 200
_COVER_WIDTH = 320
_COVER_MIN_WIDTH = 160
_MP3_BYTES_PER_SECOND = 320_000 // 8  # the MP3 encode is CBR 320k
_HANDLE = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_.]{0,29}')


def details_from_info(
    info: Mapping[str, object],
    kind: str,
    service: Service,
    options: DownloadOptions | None = None,
) -> MediaDetails | None:
    """``kind`` is 'video', 'photo' or 'collection'; None when nothing useful is known.

    The info describes yt-dlp's default choice; what the job's own format or height
    limit would change is left out rather than shown wrong.
    """
    try:
        return _details(info, kind, service, options)
    except (ValueError, TypeError, OverflowError):  # a cosmetic line never fails a download
        return None


def _details(info, kind, service, options):
    duration = _number(info.get('duration'))
    height = _count(info.get('height'))
    fps = _number(info.get('fps'))
    width = _count(info.get('width'))
    size = _size(info)
    if options is not None and options.format == 'mp3':
        width = height = fps = None
        size = int(duration * _MP3_BYTES_PER_SECOND) if duration else None
    elif options is not None and options.max_height and height and height > options.max_height:
        # A lower format will be picked: its height, frame rate and size are not known yet.
        height = fps = size = None
    details = MediaDetails(
        duration=duration,
        width=width,
        height=height,
        fps=fps,
        author=_author(info, service),
        thumbnail=_cover(info, kind),
        size_bytes=size,
        photo=kind == 'photo',
    )
    # A photo flag alone tells nothing worth a row line.
    return None if replace(details, photo=False) == MediaDetails() else details


def _number(value):
    if type(value) not in (int, float):
        return None
    try:
        value = float(value)
    except OverflowError:
        return None
    return value if math.isfinite(value) and value > 0 else None


def _count(value):
    return value if type(value) is int and 0 < value < 2**53 else None


def _size(info):
    """Expected bytes; a merged download is the sum of its parts or unknown."""
    parts = info.get('requested_formats')
    if isinstance(parts, list) and parts:
        # yt-dlp copies one part's size to the top level, which would understate a merge.
        sizes = [
            _count(p.get('filesize')) or _count(p.get('filesize_approx'))
            if isinstance(p, Mapping)
            else None
            for p in parts
        ]
        return sum(sizes) if all(sizes) else None
    return _count(info.get('filesize')) or _count(info.get('filesize_approx'))


def _author(info, service):
    if service is Service.INSTAGRAM:
        # yt-dlp's uploader is the display name there; the handle is what people know.
        for key in ('author', 'channel', 'uploader_id'):
            value = info.get(key)
            if isinstance(value, str) and _HANDLE.fullmatch(value) and not value.isdigit():
                return '@' + value
        return None
    for key in ('uploader', 'channel', 'uploader_id'):
        value = info.get(key)
        if isinstance(value, str) and value.split():
            return ' '.join(value.split())[:_AUTHOR_LIMIT]
    return None


def _cover(info, kind):
    if kind == 'photo' and is_https(info.get('url')):
        return info['url']
    if is_https(info.get('thumbnail')):
        return info['thumbnail']
    thumbnails = info.get('thumbnails')
    if not isinstance(thumbnails, list):
        return None
    candidates = [t for t in thumbnails if isinstance(t, Mapping) and is_https(t.get('url'))]
    sized = [t for t in candidates if _count(t.get('width')) and t['width'] >= _COVER_MIN_WIDTH]
    if sized:
        return min(sized, key=lambda t: abs(t['width'] - _COVER_WIDTH))['url']
    return candidates[-1]['url'] if candidates else None
