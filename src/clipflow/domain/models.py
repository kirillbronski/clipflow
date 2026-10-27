"""Immutable content identities and download parameter snapshots."""
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class Service(StrEnum):
    YOUTUBE = 'youtube'
    INSTAGRAM = 'instagram'
    GETCOURSE = 'getcourse'


class ContentKind(StrEnum):
    VIDEO = 'video'
    PLAYLIST = 'playlist'
    POST = 'post'
    PROFILE = 'profile'
    LESSON = 'lesson'
    PLAYER = 'player'


@dataclass(frozen=True)
class ParsedLink:
    service: Service
    kind: ContentKind
    canonical_id: str
    canonical_url: str


@dataclass(frozen=True)
class DownloadOptions:
    folder: Path
    format: str = 'mp4'
    max_height: int | None = None
    media_filter: str = 'all'
    author_folder: bool = True
    post_folder: bool = True
    description: str | None = None
    auth_profile: str | None = None

    def __post_init__(self):
        object.__setattr__(self, 'folder', Path(self.folder).expanduser().resolve())
        if self.format not in {'mp4', 'mkv', 'webm', 'mp3'}:
            raise ValueError('Unsupported media format')
        if self.media_filter not in {'all', 'video', 'photo'}:
            raise ValueError('Unsupported media filter')
        if self.description not in {None, 'txt', 'md'}:
            raise ValueError('Unsupported description format')
        if self.max_height is not None and (type(self.max_height) is not int or self.max_height <= 0):
            raise ValueError('Height must be a positive integer')


@dataclass(frozen=True)
class DownloadRequest:
    link: ParsedLink
    options: DownloadOptions
    selection: tuple[str, ...] | None = None
    profile_limit: int | None = None

    def __post_init__(self):
        if self.profile_limit not in (None, 10, 50):
            raise ValueError('Profile limit must be 10, 50, or all')
        if self.selection is not None:
            if not all(isinstance(item, str) and item for item in self.selection):
                raise ValueError('Selection contains an invalid media ID')
            object.__setattr__(self, 'selection', tuple(self.selection))
