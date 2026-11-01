"""Media details from extractor info: only sane values survive, nothing here raises."""

import math
from collections.abc import Mapping

from clipflow.domain.models import MediaDetails, Service, is_https

_AUTHOR_LIMIT = 200
_COVER_WIDTH = 320
_COVER_MIN_WIDTH = 160


def details_from_info(
    info: Mapping[str, object], kind: str, service: Service
) -> MediaDetails | None:
    """``kind`` is 'video', 'photo' or 'collection'; None when nothing useful is known."""
    details = MediaDetails(
        duration=_number(info.get('duration')),
        width=_count(info.get('width')),
        height=_count(info.get('height')),
        fps=_number(info.get('fps')),
        author=_author(info, service),
        thumbnail=_cover(info, kind),
        size_bytes=_count(info.get('filesize')) or _count(info.get('filesize_approx')),
    )
    return None if details == MediaDetails() else details


def _number(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        return None
    return float(value)


def _count(value):
    return value if type(value) is int and value > 0 else None


def _author(info, service):
    for key in ('uploader', 'channel', 'uploader_id'):
        value = info.get(key)
        if isinstance(value, str) and value.split():
            author = ' '.join(value.split())
            if service is Service.INSTAGRAM and not author.startswith('@'):
                author = '@' + author
            return author[:_AUTHOR_LIMIT]
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
