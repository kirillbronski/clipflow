"""Portable output names. No network, GUI, or platform storage dependencies."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import hashlib
import re
import unicodedata
from urllib.parse import urlparse
from typing import TYPE_CHECKING

from clipflow.domain.models import ContentKind, DownloadRequest, Service

if TYPE_CHECKING:
    from clipflow.providers.base import MediaItem


class UnsafePath(ValueError):
    pass


@dataclass(frozen=True)
class PostIdentity:
    code: str
    title: str | None
    published_at: datetime | None

    def __post_init__(self):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', self.code):
            raise UnsafePath('Invalid post identity')


def _units(value: str) -> int:
    return len(value.encode('utf-16-le')) // 2


def _clip(value: str, limit: int) -> str:
    while value and _units(value) > limit:
        value = value[:-1]
    return value.rstrip('. ')


def safe_name(value: str, limit: int = 56) -> str:
    text = unicodedata.normalize('NFC', value or '')
    text = text.translate(str.maketrans({'—': '-', '–': '-', '−': '-'}))
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', '-', text)
    text = re.sub(r'\s+', ' ', text).strip('. ') or 'Untitled'
    devices = {
        'CON',
        'PRN',
        'AUX',
        'NUL',
        *(f'COM{i}' for i in range(1, 10)),
        *(f'LPT{i}' for i in range(1, 10)),
    }
    if unicodedata.normalize('NFKC', text.split('.')[0]).upper() in devices:
        text = '_' + text
    return _clip(text, limit)


def _portable_identity(code: str) -> str:
    if any(c.islower() for c in code):
        case_bits = sum(1 << i for i, c in enumerate(code) if c.isupper())
        return code + f'~{case_bits:x}'
    return code


# Leaves room for a " (99)" collision suffix within the 80-unit YouTube stem.
YOUTUBE_STEM = 75


def media_identity(request: DownloadRequest, item: 'MediaItem') -> str:
    """Stable source + requested-quality marker; never shared by another video or quality."""
    identity = f'{item.id}\0{request.options.max_height}'
    if request.options.format == 'mp3':
        identity += '\0mp3:320k'
    return hashlib.sha256(identity.encode('utf-8')).hexdigest()[:16]


def _track_title(item: 'MediaItem') -> str:
    artists = item.info.get('artists')
    if not (
        isinstance(artists, list)
        and artists
        and all(isinstance(a, str) and a.strip() for a in artists)
    ):
        artist = item.info.get('artist')
        artists = [artist] if isinstance(artist, str) and artist.strip() else None
    track = item.info.get('track')
    if artists and isinstance(track, str) and track.strip():
        return ', '.join(a.strip() for a in artists) + ' - ' + track.strip()
    return item.title


def output_path(
    request: DownloadRequest, item: 'MediaItem', author: str | None, post: PostIdentity | None
) -> Path:
    if type(item.index) is not int or item.index < 1:
        raise UnsafePath('Invalid media index')
    if item.kind == 'photo':
        ext = str(item.info.get('ext', '')).lower()
        if ext not in {'jpg', 'jpeg', 'png', 'webp', 'avif'}:
            raise UnsafePath('Unsupported photograph extension')
    elif item.kind == 'video':
        ext = request.options.format
    else:
        raise UnsafePath('Unsupported media kind')
    identity_suffix = ''
    root = request.options.folder
    service = {
        Service.YOUTUBE: 'YouTube',
        Service.INSTAGRAM: 'Instagram',
        Service.GETCOURSE: 'GetCourse',
    }[request.link.service]
    directory = root / service
    if request.link.service == Service.GETCOURSE:
        if request.link.kind == ContentKind.PLAYER:
            identity = str(item.info.get('getcourse_video_hash') or item.id)
            label = 'Плеер'
        else:
            identity = (
                (urlparse(request.link.canonical_url).hostname or '')
                + '/'
                + str(item.info.get('getcourse_lesson_id') or request.link.canonical_id)
            )
            label = 'Урок'
        directory /= label + ' - ' + hashlib.sha256(identity.encode('utf-8')).hexdigest()[:12]
    if request.link.service == Service.INSTAGRAM:
        if post is None:
            raise UnsafePath('Post identity is required')
        # Instagram codes are case-sensitive, common Windows/macOS volumes are
        # not. Encode uppercase positions for codes containing lowercase so
        # case variants remain distinct without relying on a truncated hash.
        code = _portable_identity(post.code)
        if request.options.author_folder:
            directory /= safe_name(author or 'Unknown author', 30)
        if request.options.post_folder or request.link.kind == ContentKind.PROFILE:
            date = post.published_at.strftime('%Y-%m-%d - ') if post.published_at else ''
            directory /= f'{date}{safe_name(post.title or "Пост", 48)} - {code}'
            stem = f'{item.index:02d}'
        else:
            stem = f'{code} - {item.index:02d}'
    else:
        if request.playlist:
            # Owner-visible "Title [ID]"; the title already separates case-only ID variants in practice.
            identity = request.playlist.playlist_id
            directory /= (
                safe_name(request.playlist.title, 48) + ' [' + safe_name(identity, 72) + ']'
                if request.playlist.title and request.playlist.title.strip()
                else safe_name(_portable_identity(identity), 128)
            )
        position = request.playlist.index if request.playlist else item.index
        listed = request.link.kind == ContentKind.PLAYLIST or request.playlist is not None
        if request.link.service == Service.YOUTUBE:
            # Clean owner-facing names; the pipeline resolves equal names via the embedded identity tag.
            prefix = f'{position:03d} - ' if listed and request.options.numbering else ''
            stem = prefix + safe_name(_track_title(item), YOUTUBE_STEM - len(prefix))
        else:
            prefix = f'{position:03d} - ' if listed else ''
            stem = prefix + safe_name(item.title, 56 - len(prefix))
            # Titles can collide after sanitizing/truncation or case folding. Keep a
            # stable identity and requested-quality marker outside the clipped title
            # so retries reuse their own partials, never another video's bytes.
            identity_suffix = ' [' + media_identity(request, item) + ']'
    # Reserve 40 UTF-16 units for downloader/FFmpeg temporary suffixes. Root
    # folders are never shortened or redirected to make an overlong path fit.
    limit = YOUTUBE_STEM if request.link.service == Service.YOUTUBE else 56
    budget = min(limit, 200 - _units(str(directory)) - 1 - len(ext) - 1)
    if budget < _units(stem) and request.link.service == Service.INSTAGRAM:
        raise UnsafePath('Output directory is too long')
    if budget < 8:
        raise UnsafePath('Output directory is too long')
    if identity_suffix and budget <= len(identity_suffix):
        raise UnsafePath('Output directory is too long')
    target = directory / (_clip(stem, budget - len(identity_suffix)) + identity_suffix + '.' + ext)
    if not target.resolve().is_relative_to(root.resolve()):
        raise UnsafePath('Output path escapes download root')
    return target
