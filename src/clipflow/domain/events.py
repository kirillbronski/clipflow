"""Worker messages and cooperative cancellation; no UI or persistence dependencies."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import Event, Lock
from typing import Literal

from clipflow.domain.models import DownloadRequest, JobState


StopReason = Literal['pause', 'cancel', 'shutdown']


class WorkCancelled(Exception):
    def __init__(self, reason: StopReason):
        super().__init__(reason)
        self.reason = reason


class CancellationToken:
    """First cancellation wins; Event.wait makes provider delays interruptible."""

    def __init__(self):
        self._event = Event()
        self._lock = Lock()
        self._reason: StopReason | None = None

    def cancel(self, reason: StopReason) -> None:
        if reason not in {'pause', 'cancel', 'shutdown'}:
            raise ValueError('Invalid cancellation reason')
        with self._lock:
            if not self._event.is_set():
                self._reason = reason
                self._event.set()

    def raise_if_cancelled(self) -> None:
        if self._event.is_set():
            raise WorkCancelled(self._reason)

    def wait(self, timeout: float) -> bool:
        return self._event.wait(timeout)


@dataclass(frozen=True)
class StageChanged:
    state: JobState


@dataclass(frozen=True)
class TitleChanged:
    title: str


@dataclass(frozen=True)
class ProgressChanged:
    downloaded_bytes: int
    total_bytes: int | None = None
    speed_bytes_per_second: float | None = None
    eta_seconds: float | None = None


@dataclass(frozen=True)
class FilesSaved:
    files: tuple[Path, ...]


@dataclass(frozen=True)
class RequestsDiscovered:
    requests: tuple[DownloadRequest, ...]


@dataclass(frozen=True)
class SelectionRequired:
    ids: tuple[str, ...]
    titles: tuple[str, ...] = ()


@dataclass(frozen=True)
class RateLimitDeferred:
    next_allowed_at: datetime
    automatic_retry: bool
    reason: str = 'rate_limit'


@dataclass(frozen=True)
class WorkFinished:
    """Executor confirms provider returned and released its resources."""


@dataclass(frozen=True)
class WorkFailed:
    error: str  # A safe user-facing message, never a raw traceback/credential URL.


@dataclass(frozen=True)
class WorkStopped:
    """Executor acknowledges resource teardown after cancellation or deferral."""


ProviderEvent = (
    StageChanged
    | TitleChanged
    | ProgressChanged
    | FilesSaved
    | RequestsDiscovered
    | SelectionRequired
    | RateLimitDeferred
    | WorkFinished
    | WorkFailed
    | WorkStopped
)


@dataclass(frozen=True)
class JobEvent:
    job_id: str
    attempt_id: str
    payload: ProviderEvent
