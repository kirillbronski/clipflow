"""Background covers: one download at a time, shrunk to 160×90, cached for painting."""

import contextlib
import threading
import urllib.request

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QObject, QRect, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QImage, QPixmap

from clipflow.domain.models import is_https

LIMIT = 2 * 1024 * 1024
TIMEOUT = 15
SIZE = (160, 90)


def fetch_cover(url: str) -> bytes:
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 ClipFlow'})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # only https reaches here
        return response.read(LIMIT + 1)


def shrink(data: bytes) -> bytes | None:
    """A centred 16:9 crop at 160×90 as JPEG, or None when the bytes are not a picture."""
    if len(data) > LIMIT:
        return None
    image = QImage.fromData(data)
    if image.isNull() or image.width() < 1 or image.height() < 1:
        return None
    width, height = image.width(), image.height()
    if width * 9 > height * 16:
        crop = QRect((width - height * 16 // 9) // 2, 0, height * 16 // 9, height)
    else:
        crop = QRect(0, (height - width * 9 // 16) // 2, width, max(1, width * 9 // 16))
    image = image.copy(crop).scaled(
        *SIZE,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    output = QByteArray()
    buffer = QBuffer(output)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, 'JPG', 85)
    return bytes(output)


class ThumbnailLoader(QObject):
    thumbnail_ready = Signal(str)
    _fetched = Signal(str, object)

    def __init__(self, presenter, store, fetch=None):
        super().__init__(presenter)
        self.presenter = presenter
        self.store = store
        self.fetch = fetch or fetch_cover
        self._pending = {}
        self._failed = set()
        self._busy = None
        self._pixmaps = {}
        self._scheduled = False
        self._fetched.connect(self._done, Qt.ConnectionType.QueuedConnection)
        presenter.jobs_changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        """Prune covers of removed jobs and queue missing ones, once per event-loop turn."""
        if not self._scheduled:
            self._scheduled = True
            QTimer.singleShot(0, self._sync)

    def _sync(self):
        self._scheduled = False
        if self.presenter._closing:
            return
        jobs = self.presenter.repository.list()
        ids = {job.id for job in jobs}
        self.store.prune(ids)
        for job_id in [i for i in self._pixmaps if i not in ids]:
            del self._pixmaps[job_id]
        for job in jobs:
            if job.details and job.details.thumbnail:
                self.queue_cover(job.id, job.details.thumbnail)

    def queue_cover(self, job_id, url):
        if (
            job_id in self._failed
            or job_id == self._busy
            or job_id in self._pending
            or self._pixmaps.get(job_id) is not None
            or self.store.exists(job_id)
        ):
            return
        if not is_https(url):
            self._failed.add(job_id)
            return
        self._pending[job_id] = url
        self._next()

    def _next(self):
        if self._busy is not None or not self._pending or self.presenter._closing:
            return
        job_id = next(iter(self._pending))
        url = self._pending.pop(job_id)
        self._busy = job_id
        # A daemon thread: a slow cover never holds up quitting the program.
        threading.Thread(target=self._work, args=(job_id, url), daemon=True).start()

    def _work(self, job_id, url):
        try:
            data = shrink(self.fetch(url))
        except Exception:  # noqa: BLE001  # граница потока: обложка косметическая, сбой — просто без обложки
            data = None
        with contextlib.suppress(RuntimeError):  # the window may be gone by now
            self._fetched.emit(job_id, data)

    @Slot(str, object)
    def _done(self, job_id, data):
        self._busy = None
        if self.presenter._closing:
            return
        if data is None:
            self._failed.add(job_id)
        elif any(job.id == job_id for job in self.presenter.repository.list()):
            try:
                self.store.save(job_id, data)
            except OSError:
                self._failed.add(job_id)
            else:
                self._pixmaps.pop(job_id, None)
                self.thumbnail_ready.emit(job_id)
        self._next()

    def pixmap(self, job_id):
        """The cached cover; a missing file is remembered so painting never touches the disk."""
        if job_id not in self._pixmaps:
            path = self.store.path(job_id)
            pixmap = QPixmap(str(path)) if path.is_file() else QPixmap()
            self._pixmaps[job_id] = None if pixmap.isNull() else pixmap
        return self._pixmaps[job_id]
