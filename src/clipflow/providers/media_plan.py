"""Where a material will be written, decided before any network or disk access."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from clipflow.domain.models import DownloadRequest, MediaItem, Service
from clipflow.domain.paths import PostIdentity, media_identity, output_path

TAG_PREFIX = 'clipflow:'


@dataclass(frozen=True)
class MediaPlan:
    target: Path
    work: Path  # temporary download name; differs from target only when it carries identity
    tag: str | None  # YouTube identity written into the finished file's metadata
    post: PostIdentity | None


def _post(request: DownloadRequest, item: MediaItem) -> PostIdentity | None:
    if request.link.service != Service.INSTAGRAM:
        return None
    code = item.info.get('post_code') or request.link.canonical_id
    published = item.info.get('published_at')
    return PostIdentity(
        str(code),
        item.info.get('post_title'),
        published if isinstance(published, datetime) else None,
    )


def plan_media(request: DownloadRequest, item: MediaItem) -> MediaPlan:
    post = _post(request, item)
    target = output_path(request, item, item.info.get('author'), post)
    # YouTube names carry no identity: temporaries do, and finished files carry it as a tag.
    if request.link.service != Service.YOUTUBE:
        return MediaPlan(target, target, None, post)
    identity = media_identity(request, item)
    work = target.with_name(target.stem + '.' + identity)
    return MediaPlan(target, work, TAG_PREFIX + identity, post)
