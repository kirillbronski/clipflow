"""Immutable content identities and download parameter snapshots."""
from dataclasses import dataclass,replace
from datetime import datetime
from enum import StrEnum
from pathlib import Path
import re
from urllib.parse import urlsplit


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

    @property
    def is_music(self):
        return self.service==Service.YOUTUBE and urlsplit(self.canonical_url).hostname=='music.youtube.com'


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
class PlaylistPosition:
    playlist_id: str
    index: int
    title: str | None = None

    def __post_init__(self):
        if not isinstance(self.playlist_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', self.playlist_id):
            raise ValueError('Invalid playlist identity')
        if type(self.index) is not int or self.index < 1:
            raise ValueError('Playlist position must be a positive integer')
        if self.title is not None and (not isinstance(self.title,str) or len(self.title)>1000):
            raise ValueError('Invalid playlist title')


@dataclass(frozen=True)
class DownloadRequest:
    link: ParsedLink
    options: DownloadOptions
    selection: tuple[str, ...] | None = None
    profile_limit: int | None = None
    playlist: PlaylistPosition | None = None

    def __post_init__(self):
        if self.link.is_music and (self.options.format!='mp3' or self.options.max_height is not None):
            object.__setattr__(self,'options',replace(self.options,format='mp3',max_height=None))
        if self.playlist is not None and (not isinstance(self.playlist, PlaylistPosition)
                or self.link.service != Service.YOUTUBE or self.link.kind != ContentKind.VIDEO):
            raise ValueError('Playlist position belongs to a YouTube child video')
        if self.profile_limit not in (None, 10, 50):
            raise ValueError('Profile limit must be 10, 50, or all')
        if self.selection is not None:
            if not all(isinstance(item, str) and item for item in self.selection):
                raise ValueError('Selection contains an invalid media ID')
            object.__setattr__(self, 'selection', tuple(self.selection))


class JobState(StrEnum):
    QUEUED = 'queued'
    PROBING = 'probing'
    DOWNLOADING = 'downloading'
    PROCESSING = 'processing'
    COMPLETED = 'completed'
    PAUSED = 'paused'
    CANCELLED = 'cancelled'
    FAILED = 'failed'


TERMINAL_STATES = frozenset({JobState.COMPLETED, JobState.CANCELLED, JobState.FAILED})


@dataclass(frozen=True)
class Job:
    id: str
    request: DownloadRequest
    state: JobState = JobState.QUEUED
    attempt_id: str | None = None
    parent_id: str | None = None
    result_files: tuple[Path, ...] = ()
    error: str | None = None
    pause_reason: str | None = None
    next_allowed_at: datetime | None = None
    automatic_retry: bool = False
    source_required: bool = False
