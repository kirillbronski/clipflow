"""Contracts shared by providers, executor and media pipeline."""
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol, TYPE_CHECKING

from clipflow.application.ports import AuthGateway
from clipflow.domain.events import CancellationToken, ProviderEvent
from clipflow.domain.models import DownloadRequest

if TYPE_CHECKING:
    from clipflow.application.instagram_rate_policy import InstagramRatePolicy


@dataclass(frozen=True)
class MediaItem:
    id: str
    index: int
    kind: Literal['photo', 'video']
    title: str
    info: Mapping[str, object] = field(repr=False)


@dataclass(frozen=True)
class ProbeResult:
    items: tuple[MediaItem, ...]
    available_heights: tuple[int, ...]
    selection_required: bool = False
    collection_title: str | None = None


@dataclass(frozen=True)
class DownloadResult:
    files: tuple[Path, ...]
    discovered_count: int = 0


@dataclass(frozen=True)
class ExecutionContext:
    cancel: CancellationToken
    emit: Callable[[ProviderEvent], None] = field(repr=False)
    auth: AuthGateway = field(repr=False)
    instagram_rate: 'InstagramRatePolicy | None' = None


class MediaFailure(Exception):
    """Safe typed error; never retain raw CDN/auth URLs in the public message."""
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class Provider(Protocol):
    def probe(self, request: DownloadRequest, context: ExecutionContext) -> ProbeResult: ...
    def execute(self, request: DownloadRequest, context: ExecutionContext) -> DownloadResult: ...
