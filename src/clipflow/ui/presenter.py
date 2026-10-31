"""Owner-thread commands bridge submission/scheduler/storage to Qt views."""

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

from clipflow.application.history import (
    HistoryError,
    result_status,
)
from clipflow.application.probe_cache import ProbeCache
from clipflow.domain.events import RequestsDiscovered, SelectionRequired
from clipflow.domain.models import JobState
from clipflow.domain.urls import parse_url
from clipflow.ui.presenter_accounts import AccountsController
from clipflow.ui.presenter_clearing import ClearingController
from clipflow.ui.presenter_titles import TitleNamer
from clipflow.ui.queue_model import JobListModel

_UNSET = object()


class WorkbenchPresenter(QObject):
    jobs_changed = Signal()
    input_accepted = Signal(str)
    error_raised = Signal(str)
    selection_requested = Signal(str, object)
    source_requested = Signal(str)
    settings_changed = Signal()
    shutdown_finished = Signal()
    probe_ready = Signal(str, object, str)
    auth_changed = Signal()

    def __init__(self, submission, scheduler, settings, repository, *, settings_store=None):
        super().__init__()
        self.submission = submission
        self.scheduler = scheduler
        self.settings = settings
        self.repository = repository
        self.settings_store = settings_store
        self.executor = scheduler.executor
        self.executor.setParent(self)
        self.model = JobListModel(repository.list(), self)
        self._closing = False
        self.is_closed = False
        self._selections = {}
        self._probe_id = ''
        self._probe_cache = ProbeCache()
        self._clearing = ClearingController(self)
        self._accounts = AccountsController(self)
        self._close_timer = QTimer(self)
        self._close_timer.setInterval(50)
        self._close_timer.timeout.connect(self._finish_shutdown)
        self._unsubscribe = scheduler.subscribe(self._on_event)
        self.executor.closed.connect(self._finish_shutdown)
        self.executor.error.connect(self._executor_error)
        self.executor.available.connect(self._tick)
        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        # Background naming: one metadata lookup at a time, paced to stay polite to the site.
        self.title_interval_ms = 1000
        self._titles = TitleNamer(self)

    def _command(self, action):
        if self._closing:
            self.error_raised.emit('app_closed')
            return None
        try:
            return action()
        except Exception as error:  # noqa: BLE001  # команда интерфейса: любой сбой — код ошибки, окно живо
            self.error_raised.emit(getattr(error, 'code', 'action_failed'))
            return None

    def submit(self, text, mode='single', profile_limit=_UNSET):
        def action():
            limit = self.settings.profile_limit if profile_limit is _UNSET else profile_limit
            preview = self.submission.preview(text, self.settings.presets, mode, limit)
            if preview.invalid or not preview.requests:
                self.error_raised.emit('invalid_link')
                return None
            result = self._add_preview(preview)
            if result.added:
                self.input_accepted.emit(text)
            else:
                self.error_raised.emit('already_queued')
            return result

        return self._command(action)

    def _add_preview(self, preview):
        result = self.submission.submit(preview)
        self.model.set_jobs(self.repository.list())
        self.jobs_changed.emit()
        if result.added and self.settings.auto_start:
            self._start()
        return result

    def submit_preview(self, preview):
        return self._command(lambda: self._add_preview(preview))

    def update_preset(self, service, options, profile_limit=_UNSET):
        def action():
            presets = dict(self.settings.presets)
            presets[service] = options
            limit = self.settings.profile_limit if profile_limit is _UNSET else profile_limit
            settings = replace(
                self.settings,
                presets=presets,
                profile_limit=limit,
                recent_folders=(options.folder, *self.settings.recent_folders),
            )
            if settings == self.settings:
                return True
            return self._save_settings(settings)

        return self._command(action)

    def request_probe(self, text, request_id, options=None, mode='single', profile_limit=_UNSET):
        self._probe_id = request_id
        self.executor.cancel_probes()
        if not text or self._closing:
            return
        limit = self.settings.profile_limit if profile_limit is _UNSET else profile_limit
        presets = dict(self.settings.presets)
        try:
            link = parse_url(text)
            if options is not None:
                presets[link.service] = options
            preview = self.submission.preview(text, presets, mode, limit)
            if preview.invalid or not preview.requests:
                self.probe_ready.emit(request_id, (), 'invalid_link')
                return
            request = preview.requests[0]
        except ValueError:
            self.probe_ready.emit(request_id, (), 'invalid_link')
            return
        key = ProbeCache.key_for(request)
        cached = self._probe_cache.get(key)
        if cached is not None:
            self.probe_ready.emit(request_id, cached, '')
            return

        def complete(identity, heights, error):
            if identity != self._probe_id or self._closing:
                return
            if not error:
                self._probe_cache.put(key, heights)
            self.probe_ready.emit(identity, heights, error)

        self.executor.request_probe(request, request_id, complete)

    def clear_probe_cache(self):
        self._probe_cache.clear()
        self.executor.cancel_probes()
        self._probe_id = ''

    def _start(self, identity=None):
        self.executor.cancel_probes()
        self.scheduler.start(identity)

    def start_queue(self):
        return self._command(self._start)

    def _start_if_queued(self, identity):
        if self.repository.get(identity).state == JobState.QUEUED:
            self._start(identity)

    def _resume(self, identity):
        self.scheduler.resume(identity)
        self._start_if_queued(identity)

    def _retry(self, identity):
        self.scheduler.retry(identity)
        self._start_if_queued(identity)

    def _choose_items(self, identity):
        if identity in self._selections:
            self.selection_requested.emit(identity, self._selections[identity])
        else:
            self.scheduler.refresh_selection(identity)
            self._start_if_queued(identity)

    def toggle_job(self, identity):
        """Row activation: the job's state decides what the one obvious action is."""
        actions = {
            JobState.QUEUED: self._start,
            JobState.PAUSED: self._resume,
            JobState.FAILED: self._retry,
            JobState.CANCELLED: self._retry,
            JobState.COMPLETED: self.open_result,
        }

        def action():
            job = self.repository.get(identity)
            if job.source_required:
                self.source_requested.emit(identity)
            elif job.pause_reason == 'selection_required':
                self._choose_items(identity)
            else:
                actions.get(job.state, self.scheduler.pause)(identity)

        self._command(action)

    def cancel_job(self, identity):
        return self._command(lambda: self.scheduler.cancel(identity))

    def select_items(self, identity, ids):
        return self._command(lambda: self.scheduler.select_items(identity, tuple(ids)))

    def provide_source(self, identity, text):
        def action():
            self.scheduler.provide_source(identity, parse_url(text))
            self._resume(identity)

        return self._command(action)

    def open_result(self, identity):
        def action():
            job = self.repository.get(identity)
            if result_status(job) == 'files_missing':
                raise HistoryError('files_missing')
            directory = (
                job.result_files[0].parent if job.result_files else job.request.options.folder
            )
            if not directory.is_dir():
                self.error_raised.emit('folder_missing')
                return
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory))):
                self.error_raised.emit('folder_missing')

        return self._command(action)

    def _reload_jobs(self):
        self.model.set_jobs(self.repository.list())
        self.jobs_changed.emit()

    def repeat_job(self, identity):
        def action():
            job = self.repository.get(identity)
            if job.source_required:
                self.source_requested.emit(identity)
                return
            if job.state in {JobState.FAILED, JobState.CANCELLED}:
                self.scheduler.retry(identity)
            else:
                self.submission.repeat(identity)
            self._reload_jobs()
            if self.settings.auto_start:
                self._start()

        return self._command(action)

    def remove_jobs(self, identities):
        return self._command(lambda: self._clearing.remove_jobs(identities))

    def clear_history(self):
        return self._command(self._clearing.clear_history)

    def clear_queue(self):
        return self._command(self._clearing.clear_queue)

    def cancel_queue(self):
        # Scheduler cancels every service and stops pumping before worker ACK.
        return self._command(self.scheduler.clear_queue)

    def clear_all(self, *, delete_files=False):
        return self._command(lambda: self._clearing.clear_all(delete_files))

    def _flush_clear(self):
        self._clearing.flush()

    def delete_files(self, job_ids, confirmed=False):
        if confirmed is not True:
            return None
        return self._command(lambda: self._clearing.delete_files(job_ids))

    def update_folder(self, service, path):
        def action():
            presets = dict(self.settings.presets)
            folder = Path(path).expanduser().resolve()
            presets[service] = replace(presets[service], folder=folder)
            return self._save_settings(
                replace(
                    self.settings,
                    presets=presets,
                    recent_folders=(folder, *self.settings.recent_folders),
                )
            )

        return self._command(action)

    def set_auto_start(self, enabled):
        return self._command(
            lambda: self._save_settings(replace(self.settings, auto_start=enabled))
        )

    def update_preferences(self, **values):
        return self._command(lambda: self._save_settings(replace(self.settings, **values)))

    @property
    def auth_gateway(self):
        return self._accounts.gateway

    @auth_gateway.setter
    def auth_gateway(self, gateway):
        self._accounts.gateway = gateway

    def set_auth_gateway(self, gateway):
        self._accounts.attach(gateway)

    def _poll_auth(self):
        if self._closing or self.auth_gateway is None:
            return
        self._command(self._accounts.poll)

    def sign_in_account(self, service):
        if self.auth_gateway is not None:
            return self._command(lambda: self._accounts.sign_in(service))
        return None

    def logout_account(self, service):
        return self._command(lambda: self._accounts.logout(service))

    def configure_getcourse(self, url, method, **values):
        return self._command(lambda: self._accounts.configure_getcourse(url, method, **values))

    def import_getcourse(self, url):
        return self._command(lambda: self._accounts.import_getcourse(url))

    def _save_settings(self, settings):
        if self.settings_store:
            self.settings_store.save(settings)
        self.settings = settings
        self.settings_changed.emit()
        return True

    def _on_event(self, event):
        job = self.repository.get(event.job_id)
        self.model.update_job(job, event.payload)
        if isinstance(event.payload, RequestsDiscovered):
            self.model.set_jobs(self.repository.list())
        if isinstance(event.payload, SelectionRequired):
            self._selections[job.id] = event.payload
            self.selection_requested.emit(job.id, event.payload)
        self.jobs_changed.emit()

    @Slot()
    def _tick(self):
        if not self._closing:
            self._command(self._flush_clear)
            self._command(self.scheduler.tick)
            self._titles.schedule()

    @Slot(str)
    def _executor_error(self, code):
        self.error_raised.emit(code)
        if code == 'queue_update_failed':
            self.shutdown()

    def shutdown(self):
        if self._closing:
            return
        self._closing = True
        self._timer.stop()
        self._accounts.stop()
        self._titles.stop()
        if self.auth_gateway is not None:
            self.auth_gateway.close()
        try:
            self.scheduler.shutdown()
        except Exception:  # noqa: BLE001  # закрытие: сбой записи очереди — код ошибки, выход продолжается
            self.error_raised.emit('queue_update_failed')
        self.executor.shutdown()

    @Slot()
    def _finish_shutdown(self):
        if self.is_closed:
            return
        if self.auth_gateway is not None and not self.auth_gateway.is_closed:
            self._close_timer.start()
            return
        self._close_timer.stop()
        self._unsubscribe()
        close = getattr(self.repository, 'close', None)
        if close:
            close()
        self.is_closed = True
        self.shutdown_finished.emit()
