"""Provider workers with queued owner-thread delivery and teardown acknowledgements."""
import time

from PySide6.QtCore import QObject,QThread,Signal,Slot,Qt,QCoreApplication

from clipflow.domain.events import (
    CancellationToken,JobEvent,ProgressChanged,WorkCancelled,WorkFailed,WorkFinished,WorkStopped,
)
from clipflow.providers.base import ExecutionContext,MediaFailure


class _Worker(QThread):
    event=Signal(object)

    def __init__(self,job,provider,auth,policy,parent):
        super().__init__(parent)
        self.job=job; self.provider=provider; self.auth=auth; self.policy=policy
        self.cancel=CancellationToken(); self.terminal=WorkFailed('worker_failed')
        self._last_progress=-float('inf')

    def _emit(self,payload):
        if isinstance(payload,(WorkFinished,WorkFailed,WorkStopped)):
            raise MediaFailure('invalid_provider_event')
        if isinstance(payload,ProgressChanged):
            now=time.monotonic()
            if now-self._last_progress<.5: return
            self._last_progress=now
        self.event.emit(JobEvent(self.job.id,self.job.attempt_id,payload))

    def run(self):
        try:
            self.cancel.raise_if_cancelled()
            context=ExecutionContext(self.cancel,self._emit,self.auth,self.policy)
            self.provider.execute(self.job.request,context)
            self.cancel.raise_if_cancelled()
            self.terminal=WorkFinished()
        except WorkCancelled: self.terminal=WorkStopped()
        except MediaFailure as error: self.terminal=WorkFailed(str(error))
        except Exception: self.terminal=WorkFailed('worker_failed')
        # QThread.finished is emitted only after run() returns and provider
        # context managers have closed their HTTP/process resources.


class ThreadExecutor(QObject):
    closed=Signal()
    error=Signal(str)

    def __init__(self,provider_registry,auth_gateway,*,instagram_rate=None,cleanup=None):
        super().__init__()
        self.registry=provider_registry; self.auth=auth_gateway; self.instagram_rate=instagram_rate
        self._cleanup=cleanup or (lambda:None)
        self._workers={}; self._closing=False; self._closed=False

    @property
    def is_idle(self): return not self._workers

    @property
    def is_closed(self): return self._closed

    def start(self,job,on_event):
        if self._closing or self._workers: raise ValueError('Executor unavailable')
        provider=self.registry[(job.request.link.service,job.request.link.kind)]
        worker=_Worker(job,provider,self.auth,self.instagram_rate,self)
        self._workers[(job.id,job.attempt_id)]=(worker,on_event)
        worker.event.connect(self._deliver,Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(self._finished,Qt.ConnectionType.QueuedConnection)
        worker.start()

    def stop(self,job_id,reason):
        for (identity,_),(worker,_) in tuple(self._workers.items()):
            if identity==job_id: worker.cancel.cancel(reason)

    @Slot(object)
    def _deliver(self,event):
        record=self._workers.get((event.job_id,event.attempt_id))
        if record:
            try: record[1](event)
            except Exception:
                record[0].cancel.cancel('pause')
                self.error.emit('queue_update_failed')

    @Slot()
    def _finished(self): self._finish_worker(self.sender())

    def _finish_worker(self,worker):
        key=(worker.job.id,worker.job.attempt_id)
        record=self._workers.pop(key,None)
        if record is None: return
        worker.wait()
        try: record[1](JobEvent(*key,worker.terminal))
        except Exception: self.error.emit('queue_update_failed')
        worker.deleteLater()
        self._try_close()

    def shutdown(self):
        self._closing=True
        for worker,_ in tuple(self._workers.values()): worker.cancel.cancel('shutdown')
        self._try_close()

    def _try_close(self):
        if self._closing and not self._workers and not self._closed:
            try: self._cleanup()
            except Exception: self.error.emit('worker_cleanup_failed')
            self._closed=True
            self.closed.emit()

    def drain(self):
        """After QApplication.exec exits: reap workers, never destroy a live QThread."""
        self.shutdown()
        while self._workers:
            QCoreApplication.processEvents()
            for worker,_ in tuple(self._workers.values()):
                if worker.wait(25): self._finish_worker(worker)
