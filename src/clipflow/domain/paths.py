"""Portable output names. No network, GUI, or platform storage dependencies."""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
import unicodedata
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
    devices = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}
    if unicodedata.normalize('NFKC', text.split('.')[0]).upper() in devices:
        text = '_' + text
    return _clip(text, limit)


def output_path(request: DownloadRequest, item: 'MediaItem', author: str | None,
                post: PostIdentity | None) -> Path:
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
    root = request.options.folder
    service = {Service.YOUTUBE: 'YouTube', Service.INSTAGRAM: 'Instagram', Service.GETCOURSE: 'GetCourse'}[request.link.service]
    directory = root/service
    if request.link.service == Service.INSTAGRAM:
        if post is None:
            raise UnsafePath('Post identity is required')
        # Instagram codes are case-sensitive, common Windows/macOS volumes are
        # not. Encode uppercase positions for codes containing lowercase so
        # case variants remain distinct without relying on a truncated hash.
        code = post.code
        if any(c.islower() for c in code):
            case_bits = sum(1 << i for i, c in enumerate(code) if c.isupper())
            code += f'~{case_bits:x}'
        if request.options.author_folder:
            directory /= safe_name(author or 'Unknown author', 30)
        if request.options.post_folder or request.link.kind == ContentKind.PROFILE:
            date = post.published_at.strftime('%Y-%m-%d - ') if post.published_at else ''
            directory /= f'{date}{safe_name(post.title or "Пост", 48)} - {code}'
            stem = f'{item.index:02d}'
        else:
            stem = f'{code} - {item.index:02d}'
    else:
        prefix = f'{item.index:03d} - ' if request.link.kind == ContentKind.PLAYLIST else ''
        stem = prefix + safe_name(item.title, 56 - len(prefix))
    # Reserve 40 UTF-16 units for downloader/FFmpeg temporary suffixes. Root
    # folders are never shortened or redirected to make an overlong path fit.
    budget = min(56, 200 - _units(str(directory)) - 1 - len(ext) - 1)
    if budget < _units(stem) and request.link.service == Service.INSTAGRAM:
        raise UnsafePath('Output directory is too long')
    if budget < 8:
        raise UnsafePath('Output directory is too long')
    target = directory/(_clip(stem, budget) + '.' + ext)
    if not target.resolve().is_relative_to(root.resolve()):
        raise UnsafePath('Output path escapes download root')
    return target
