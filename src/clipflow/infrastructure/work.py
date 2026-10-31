"""What worker threads run, as plain functions: every outcome becomes a safe result."""

import time
from collections.abc import Callable

from clipflow.domain.events import (
    ProgressChanged,
    WorkCancelled,
    WorkFailed,
    WorkFinished,
    WorkStopped,
)
from clipflow.domain.models import ContentKind
from clipflow.providers.base import MediaFailure

_TERMINAL = (WorkFinished, WorkFailed, WorkStopped)


def _skips_quality_probe(request):
    # Collections choose formats per material, never enumerate twice for quality.
    return (
        request.link.kind in {ContentKind.PROFILE, ContentKind.PLAYLIST}
        or request.options.format == 'mp3'
        or request.options.media_filter == 'photo'
    )


def run_probe(request, provider, context) -> tuple[tuple[int, ...], str]:
    """Available heights, highest first, and an error code ('' when none)."""
    try:
        context.cancel.raise_if_cancelled()
        if _skips_quality_probe(request):
            return (), ''
        result = provider.probe(request, context)
        context.cancel.raise_if_cancelled()
        heights = {h for h in result.available_heights if type(h) is int and h > 0}
        return tuple(sorted(heights, reverse=True)), ''
    except WorkCancelled as error:
        return (), 'rate_limit' if hasattr(error, 'decision') else 'probe_cancelled'
    except MediaFailure as error:
        return (), error.code
    except Exception:  # noqa: BLE001  # подпроект 3
        return (), 'probe_failed'


def run_title(request, provider, context) -> str | None:
    try:
        title = provider.planned_title(request, context)
        context.cancel.raise_if_cancelled()
    except Exception:  # noqa: BLE001  # подпроект 3
        return None  # names are cosmetic: never surface lookup errors
    return title if isinstance(title, str) and title.strip() else None


def run_download(request, provider, context) -> WorkFinished | WorkStopped | WorkFailed:
    try:
        context.cancel.raise_if_cancelled()
        provider.execute(request, context)
        context.cancel.raise_if_cancelled()
        return WorkFinished()
    except WorkCancelled:
        return WorkStopped()
    except MediaFailure as error:
        return WorkFailed(str(error))
    except Exception:  # noqa: BLE001  # подпроект 3
        return WorkFailed('worker_failed')


def check_provider_event(payload):
    """Only the worker acknowledges the end of a job; a provider may not."""
    if isinstance(payload, _TERMINAL):
        raise MediaFailure('invalid_provider_event')


class ProgressThrottle:
    """At most one progress event per interval; every other event passes."""

    def __init__(self, interval: float = 0.5, clock: Callable[[], float] = time.monotonic):
        self.interval = interval
        self.clock = clock
        self._last = -float('inf')

    def allow(self, payload) -> bool:
        if not isinstance(payload, ProgressChanged):
            return True
        now = self.clock()
        if now - self._last < self.interval:
            return False
        self._last = now
        return True
