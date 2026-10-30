"""Provider workers with queued owner-thread delivery and teardown acknowledgements."""

import time

from PySide6.QtCore import QObject, QThread, Signal, Slot, Qt, QCoreApplication

from clipflow.domain.events import (
    CancellationToken,
    JobEvent,
    ProgressChanged,
    WorkCancelled,
    WorkFailed,
    WorkFinished,
    WorkStopped,
)
from clipflow.providers.base import ExecutionContext, MediaFailure
from clipflow.domain.models import ContentKind


class _ProbeWorker(QThread):
    def __init__(self, request, request_id, provider, auth, policy, parent):
        super().__init__(parent)
        self.request = request
        self.request_id = request_id
        self.provider = provider
        self.auth = auth
        self.policy = policy
        self.cancel = CancellationToken()
        self.heights = ()
        self.error = ''

    def run(self):
        try:
            self.cancel.raise_if_cancelled()
            if (
                self.request.link.kind in {ContentKind.PROFILE, ContentKind.PLAYLIST}
                or self.request.options.format == 'mp3'
                or self.request.options.media_filter == 'photo'
            ):
                return  # Collections choose formats per material, never enumerate twice for quality.
            context = ExecutionContext(self.cancel, lambda event: None, self.auth, self.policy)
            result = self.provider.probe(self.request, context)
            self.cancel.raise_if_cancelled()
            self.heights = tuple(
                sorted(
                    {
                        height
                        for height in result.available_heights
                        if type(height) is int and height > 0
                    },
                    reverse=True,
                )
            )
        except WorkCancelled as error:
            self.error = 'rate_limit' if hasattr(error, 'decision') else 'probe_cancelled'
        except MediaFailure as error:
            self.error = error.code
        except Exception:
            self.error = 'probe_failed'


class _TitleWorker(QThread):
    def __init__(self, job, provider, auth, parent):
        super().__init__(parent)
        self.job = job
        self.provider = provider
        self.auth = auth
        self.cancel = CancellationToken()
        self.title = None

    def run(self):
        try:
            context = ExecutionContext(self.cancel, lambda event: None, self.auth)
            title = self.provider.planned_title(self.job.request, context)
            self.cancel.raise_if_cancelled()
            self.title = title if isinstance(title, str) and title.strip() else None
        except Exception:
            self.title = None  # names are cosmetic: never surface lookup errors


class _Worker(QThread):
    event = Signal(object)

    def __init__(self, job, provider, auth, policy, parent):
        super().__init__(parent)
        self.job = job
        self.provider = provider
        self.auth = auth
        self.policy = policy
        self.cancel = CancellationToken()
        self.terminal = WorkFailed('worker_failed')
        self._last_progress = -float('inf')

    def _emit(self, payload):
        if isinstance(payload, (WorkFinished, WorkFailed, WorkStopped)):
            raise MediaFailure('invalid_provider_event')
        if isinstance(payload, ProgressChanged):
            now = time.monotonic()
            if now - self._last_progress < 0.5:
                return
            self._last_progress = now
        self.event.emit(JobEvent(self.job.id, self.job.attempt_id, payload))

    def run(self):
        try:
            self.cancel.raise_if_cancelled()
            context = ExecutionContext(self.cancel, self._emit, self.auth, self.policy)
            self.provider.execute(self.job.request, context)
            self.cancel.raise_if_cancelled()
            self.terminal = WorkFinished()
        except WorkCancelled:
            self.terminal = WorkStopped()
        except MediaFailure as error:
            self.terminal = WorkFailed(str(error))
        except Exception:
            self.terminal = WorkFailed('worker_failed')
        # QThread.finished is emitted only after run() returns and provider
        # context managers have closed their HTTP/process resources.


class ThreadExecutor(QObject):
    closed = Signal()
    error = Signal(str)
    available = Signal()

    def __init__(self, provider_registry, auth_gateway, *, instagram_rate=None, cleanup=None):
        super().__init__()
        self.registry = provider_registry
        self.auth = auth_gateway
        self.instagram_rate = instagram_rate
        self._cleanup = cleanup or (lambda: None)
        self._workers = {}
        self._closing = False
        self._closed = False
        self._probe = None
        self._pending_probe = None
        self._naming = None

    @property
    def is_idle(self):
        return not self._workers and self._probe is None

    @property
    def is_closed(self):
        return self._closed

    def start(self, job, on_event):
        if self._closing or not self.is_idle:
            raise ValueError('Executor unavailable')
        provider = self.registry[(job.request.link.service, job.request.link.kind)]
        worker = _Worker(job, provider, self.auth, self.instagram_rate, self)
        self._workers[(job.id, job.attempt_id)] = (worker, on_event)
        worker.event.connect(self._deliver, Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(self._finished, Qt.ConnectionType.QueuedConnection)
        worker.start()

    def stop(self, job_id, reason):
        for (identity, _), (worker, _) in tuple(self._workers.items()):
            if identity == job_id:
                worker.cancel.cancel(reason)

    @Slot(object)
    def _deliver(self, event):
        record = self._workers.get((event.job_id, event.attempt_id))
        if record:
            try:
                record[1](event)
            except Exception:
                record[0].cancel.cancel('pause')
                self.error.emit('queue_update_failed')

    @Slot()
    def _finished(self):
        self._finish_worker(self.sender())

    def _finish_worker(self, worker):
        key = (worker.job.id, worker.job.attempt_id)
        record = self._workers.pop(key, None)
        if record is None:
            return
        worker.wait()
        try:
            record[1](JobEvent(*key, worker.terminal))
        except Exception:
            self.error.emit('queue_update_failed')
        worker.deleteLater()
        self._start_probe()
        self._try_close()
        if self.is_idle and not self._closing:
            self.available.emit()

    def can_name(self, job):
        return callable(
            getattr(
                self.registry.get((job.request.link.service, job.request.link.kind)),
                'planned_title',
                None,
            )
        )

    @property
    def naming(self):
        return self._naming is not None

    def request_title(self, job, callback):
        """One background name lookup at a time, beside (not instead of) the download slot."""
        if self._closing or self._naming is not None or not self.can_name(job):
            return False
        worker = _TitleWorker(
            job, self.registry[(job.request.link.service, job.request.link.kind)], self.auth, self
        )
        self._naming = (worker, callback)
        worker.finished.connect(self._title_finished, Qt.ConnectionType.QueuedConnection)
        worker.start()
        return True

    @Slot()
    def _title_finished(self):
        self._finish_title(self.sender())

    def _finish_title(self, worker):
        if self._naming is None or self._naming[0] is not worker:
            return
        _, callback = self._naming
        self._naming = None
        worker.wait()
        if not self._closing:
            try:
                callback(worker.job.id, worker.title)
            except Exception:
                self.error.emit('queue_update_failed')
        worker.deleteLater()
        self._try_close()

    def request_probe(self, request, request_id, callback):
        if self._closing:
            return
        self.cancel_probes()
        self._pending_probe = (request, request_id, callback)
        self._start_probe()

    def cancel_probes(self):
        self._pending_probe = None
        if self._probe:
            self._probe[0].cancel.cancel('cancel')

    def _start_probe(self):
        if self._closing or not self.is_idle or self._pending_probe is None:
            return
        request, request_id, callback = self._pending_probe
        self._pending_probe = None
        provider = self.registry.get((request.link.service, request.link.kind))
        worker = _ProbeWorker(request, request_id, provider, self.auth, self.instagram_rate, self)
        self._probe = (worker, callback)
        worker.finished.connect(self._probe_finished, Qt.ConnectionType.QueuedConnection)
        worker.start()

    @Slot()
    def _probe_finished(self):
        self._finish_probe(self.sender())

    def _finish_probe(self, worker):
        if self._probe is None or self._probe[0] is not worker:
            return
        _, callback = self._probe
        self._probe = None
        worker.wait()
        if not self._closing:
            try:
                callback(worker.request_id, worker.heights, worker.error)
            except Exception:
                self.error.emit('probe_failed')
        worker.deleteLater()
        self._start_probe()
        self._try_close()
        if self.is_idle and not self._closing:
            self.available.emit()

    def shutdown(self):
        self._closing = True
        self.cancel_probes()
        if self._naming:
            self._naming[0].cancel.cancel('shutdown')
        for worker, _ in tuple(self._workers.values()):
            worker.cancel.cancel('shutdown')
        self._try_close()

    def _try_close(self):
        if self._closing and self.is_idle and self._naming is None and not self._closed:
            try:
                self._cleanup()
            except Exception:
                self.error.emit('worker_cleanup_failed')
            self._closed = True
            self.closed.emit()

    def drain(self):
        """After QApplication.exec exits: reap workers, never destroy a live QThread."""
        self.shutdown()
        while not self.is_idle or self._naming is not None:
            QCoreApplication.processEvents()
            if self._naming and self._naming[0].wait(25):
                self._finish_title(self._naming[0])
            for worker, _ in tuple(self._workers.values()):
                if worker.wait(25):
                    self._finish_worker(worker)
            if self._probe and self._probe[0].wait(25):
                self._finish_probe(self._probe[0])
