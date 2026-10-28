"""Owner-thread commands bridge submission/scheduler/storage to Qt views."""
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QObject,QTimer,Signal,Slot,QUrl
from PySide6.QtGui import QDesktopServices

from clipflow.domain.events import RequestsDiscovered,SelectionRequired
from clipflow.domain.models import JobState,TERMINAL_STATES
from clipflow.domain.urls import parse_url
from clipflow.ui.queue_model import JobListModel


class WorkbenchPresenter(QObject):
    jobs_changed=Signal()
    input_accepted=Signal(str)
    error_raised=Signal(str)
    selection_requested=Signal(str,object)
    source_requested=Signal(str)
    settings_changed=Signal()
    shutdown_finished=Signal()

    def __init__(self,submission,scheduler,settings,repository,*,settings_store=None):
        super().__init__()
        self.submission=submission; self.scheduler=scheduler; self.settings=settings; self.repository=repository
        self.settings_store=settings_store; self.executor=scheduler.executor
        self.executor.setParent(self)
        self.model=JobListModel(repository.list(),self)
        self._closing=False; self.is_closed=False; self._selections={}
        self._unsubscribe=scheduler.subscribe(self._on_event)
        self.executor.closed.connect(self._finish_shutdown)
        self.executor.error.connect(self._executor_error)
        self._timer=QTimer(self); self._timer.setInterval(500); self._timer.timeout.connect(self._tick); self._timer.start()

    def _command(self,action):
        if self._closing:
            self.error_raised.emit('app_closed'); return None
        try: return action()
        except Exception as error:
            code=getattr(error,'code','action_failed')
            if isinstance(error,ValueError) and str(error).startswith('Source changed'): code='source_changed'
            elif isinstance(error,ValueError) and 'Cooldown' in str(error): code='cooldown_active'
            self.error_raised.emit(code); return None

    def submit(self,text,mode='single'):
        def action():
            preview=self.submission.preview(text,self.settings.presets,mode,self.settings.profile_limit)
            if preview.invalid or not preview.requests:
                self.error_raised.emit('invalid_link'); return None
            result=self.submission.submit(preview)
            self.model.set_jobs(self.repository.list()); self.jobs_changed.emit()
            if result.added:
                self.input_accepted.emit(text)
                if self.settings.auto_start: self.scheduler.start()
            else: self.error_raised.emit('already_queued')
            return result
        return self._command(action)

    def start_queue(self): return self._command(self.scheduler.start)

    def toggle_job(self,identity):
        def action():
            job=self.repository.get(identity)
            if job.source_required: self.source_requested.emit(identity); return
            if job.pause_reason=='selection_required':
                if identity in self._selections: self.selection_requested.emit(identity,self._selections[identity])
                else:
                    self.scheduler.refresh_selection(identity)
                    if self.repository.get(identity).state==JobState.QUEUED: self.scheduler.start(identity)
                return
            if job.state==JobState.QUEUED: self.scheduler.start(identity)
            elif job.state==JobState.PAUSED:
                self.scheduler.resume(identity)
                if self.repository.get(identity).state==JobState.QUEUED: self.scheduler.start(identity)
            elif job.state in {JobState.FAILED,JobState.CANCELLED}:
                self.scheduler.retry(identity)
                if self.repository.get(identity).state==JobState.QUEUED: self.scheduler.start(identity)
            elif job.state==JobState.COMPLETED: self.open_result(identity)
            else: self.scheduler.pause(identity)
        self._command(action)

    def cancel_job(self,identity): return self._command(lambda:self.scheduler.cancel(identity))
    def select_items(self,identity,ids): return self._command(lambda:self.scheduler.select_items(identity,tuple(ids)))

    def provide_source(self,identity,text):
        def action():
            self.scheduler.provide_source(identity,parse_url(text)); self.scheduler.resume(identity)
            if self.repository.get(identity).state==JobState.QUEUED: self.scheduler.start(identity)
        return self._command(action)

    def open_result(self,identity):
        def action():
            job=self.repository.get(identity)
            directory=job.result_files[0].parent if job.result_files else job.request.options.folder
            if not directory.is_dir(): self.error_raised.emit('folder_missing'); return
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory))): self.error_raised.emit('folder_missing')
        return self._command(action)

    def update_folder(self,service,path):
        def action():
            presets=dict(self.settings.presets); folder=Path(path).expanduser().resolve()
            presets[service]=replace(presets[service],folder=folder)
            return self._save_settings(replace(self.settings,presets=presets,recent_folders=(folder,*self.settings.recent_folders)))
        return self._command(action)

    def set_auto_start(self,enabled):
        return self._command(lambda:self._save_settings(replace(self.settings,auto_start=enabled)))

    def _save_settings(self,settings):
        if self.settings_store: self.settings_store.save(settings)
        self.settings=settings; self.settings_changed.emit()
        return True

    def _on_event(self,event):
        job=self.repository.get(event.job_id)
        self.model.update_job(job,event.payload)
        if isinstance(event.payload,RequestsDiscovered): self.model.set_jobs(self.repository.list())
        if isinstance(event.payload,SelectionRequired):
            self._selections[job.id]=event.payload
            self.selection_requested.emit(job.id,event.payload)
        self.jobs_changed.emit()

    @Slot()
    def _tick(self):
        if not self._closing: self._command(self.scheduler.tick)

    @Slot(str)
    def _executor_error(self,code):
        self.error_raised.emit(code)
        if code=='queue_update_failed': self.shutdown()

    def shutdown(self):
        if self._closing: return
        self._closing=True; self._timer.stop()
        try: self.scheduler.shutdown()
        except Exception: self.error_raised.emit('queue_update_failed')
        self.executor.shutdown()

    @Slot()
    def _finish_shutdown(self):
        self._unsubscribe()
        close=getattr(self.repository,'close',None)
        if close: close()
        self.is_closed=True; self.shutdown_finished.emit()
