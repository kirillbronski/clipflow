"""Recent link checks are reused for a short while so typing does not re-query the site."""

import time
from collections.abc import Callable

from clipflow.domain.models import DownloadRequest


class ProbeCache:
    def __init__(
        self,
        *,
        ttl: float = 120.0,
        limit: int = 100,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.ttl = ttl
        self.limit = limit
        self.clock = clock
        self._entries: dict[tuple, tuple[float, tuple[int, ...]]] = {}

    @staticmethod
    def key_for(request: DownloadRequest) -> tuple:
        """Qualities depend on the material, the signed-in profile and audio-only mode."""
        options = request.options
        return (
            request.link.service,
            request.link.kind,
            request.link.canonical_id,
            options.auth_profile,
            options.media_filter,
            options.format == 'mp3',
        )

    def get(self, key: tuple) -> tuple[int, ...] | None:
        entry = self._entries.get(key)
        if entry and self.clock() - entry[0] < self.ttl:
            return entry[1]
        return None

    def put(self, key: tuple, heights: tuple[int, ...]) -> None:
        if len(self._entries) >= self.limit:
            self._entries.pop(next(iter(self._entries)))
        self._entries[key] = (self.clock(), heights)

    def clear(self) -> None:
        self._entries.clear()
