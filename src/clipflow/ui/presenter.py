"""Owner-thread commands bridge submission/scheduler/storage to Qt views."""

import time
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

from clipflow.domain.events import RequestsDiscovered, SelectionRequired
from clipflow.domain.models import TERMINAL_STATES, JobState, Service
from clipflow.domain.urls import parse_url
from clipflow.ui.history import HistoryError, deletion_paths, result_status
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
        self._probe_cache = {}
        self._clear_pending = set()
        self._clear_delete_ids = set()
        self.auth_gateway = None
        self._auth_snapshot = None
        self._auth_timer = QTimer(self)
        self._auth_timer.setInterval(1000)
        self._auth_timer.timeout.connect(self._poll_auth)
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
        self._titled = set()
        self._title_timer = QTimer(self)
        self._title_timer.setSingleShot(True)
        self._title_timer.timeout.connect(self._name_next)

    def _command(self, action):
        if self._closing:
            self.error_raised.emit('app_closed')
            return None
        try:
            return action()
        except Exception as error:
            code = getattr(error, 'code', 'action_failed')
            if isinstance(error, ValueError) and str(error).startswith('Source changed'):
                code = 'source_changed'
            elif isinstance(error, ValueError) and 'Cooldown' in str(error):
                code = 'cooldown_active'
            self.error_raised.emit(code)
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
        key = (
            link.service,
            request.link.kind,
            request.link.canonical_id,
            request.options.auth_profile,
            request.options.media_filter,
            request.options.format == 'mp3',
        )
        cached = self._probe_cache.get(key)
        if cached and time.monotonic() - cached[0] < 120:
            self.probe_ready.emit(request_id, cached[1], '')
            return

        def complete(identity, heights, error):
            if identity != self._probe_id or self._closing:
                return
            if not error:
                if len(self._probe_cache) >= 100:
                    self._probe_cache.pop(next(iter(self._probe_cache)))
                self._probe_cache[key] = (time.monotonic(), heights)
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

    def toggle_job(self, identity):
        def action():
            job = self.repository.get(identity)
            if job.source_required:
                self.source_requested.emit(identity)
                return
            if job.pause_reason == 'selection_required':
                if identity in self._selections:
                    self.selection_requested.emit(identity, self._selections[identity])
                else:
                    self.scheduler.refresh_selection(identity)
                    if self.repository.get(identity).state == JobState.QUEUED:
                        self._start(identity)
                return
            if job.state == JobState.QUEUED:
                self._start(identity)
            elif job.state == JobState.PAUSED:
                self.scheduler.resume(identity)
                if self.repository.get(identity).state == JobState.QUEUED:
                    self._start(identity)
            elif job.state in {JobState.FAILED, JobState.CANCELLED}:
                self.scheduler.retry(identity)
                if self.repository.get(identity).state == JobState.QUEUED:
                    self._start(identity)
            elif job.state == JobState.COMPLETED:
                self.open_result(identity)
            else:
                self.scheduler.pause(identity)

        self._command(action)

    def cancel_job(self, identity):
        return self._command(lambda: self.scheduler.cancel(identity))

    def select_items(self, identity, ids):
        return self._command(lambda: self.scheduler.select_items(identity, tuple(ids)))

    def provide_source(self, identity, text):
        def action():
            self.scheduler.provide_source(identity, parse_url(text))
            self.scheduler.resume(identity)
            if self.repository.get(identity).state == JobState.QUEUED:
                self._start(identity)

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
        def action():
            jobs = tuple(self.repository.get(identity) for identity in identities)
            if not self.executor.is_idle or any(j.state not in TERMINAL_STATES for j in jobs):
                raise HistoryError('job_busy')
            self.repository.remove(identities)
            self._reload_jobs()

        return self._command(action)

    def clear_history(self):
        def action():
            if not self.executor.is_idle:
                raise HistoryError('job_busy')
            self.repository.clear_history()
            self._reload_jobs()

        return self._command(action)

    def clear_queue(self):
        def action():
            self._clear_pending.update(self.scheduler.clear_queue())
            self._flush_clear()

        return self._command(action)

    def cancel_queue(self):
        # Scheduler cancels every service and stops pumping before worker ACK.
        return self._command(self.scheduler.clear_queue)

    def clear_all(self, *, delete_files=False):
        def action():
            identities = {job.id for job in self.repository.list()}
            if not identities:
                return
            self._clear_pending.update(identities)
            # A later confirmation applies only to its own target snapshot.
            # In particular an unchecked dialog revokes deletion for those IDs.
            self._clear_delete_ids.difference_update(identities)
            if delete_files:
                self._clear_delete_ids.update(identities)
            self.scheduler.clear_queue()
            self._flush_clear()

        return self._command(action)

    def _flush_clear(self):
        if not self._clear_pending or not self.executor.is_idle:
            return
        jobs = self.repository.list()
        targets = self._clear_pending.copy()
        # A completed child may still need its original parent; retain ancestors.
        while True:
            parents = {j.parent_id for j in jobs if j.id not in targets}
            smaller = targets - parents
            if smaller == targets:
                break
            targets = smaller
        delete_ids = targets & self._clear_delete_ids
        # Never retry destructive IO on the periodic tick after an error.
        self._clear_pending.clear()
        self._clear_delete_ids = set()
        if delete_ids:
            selected = tuple(job for job in jobs if job.id in delete_ids)
            paths = deletion_paths(selected, jobs)
            try:
                for path in paths:
                    path.unlink(missing_ok=True)
            except OSError:
                self._reload_jobs()
                raise HistoryError('file_delete_failed') from None
        self.repository.remove(tuple(targets))
        self._reload_jobs()

    def delete_files(self, job_ids, confirmed=False):
        if confirmed is not True:
            return

        def action():
            if not self.executor.is_idle:
                raise HistoryError('job_busy')
            jobs = tuple(self.repository.get(identity) for identity in job_ids)
            paths = deletion_paths(jobs, self.repository.list())
            try:
                for path in paths:
                    path.unlink(missing_ok=True)
            except OSError:
                raise HistoryError('file_delete_failed') from None
            finally:
                self._reload_jobs()

        return self._command(action)

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

    def set_auth_gateway(self, gateway):
        self.auth_gateway = gateway
        self.executor.auth = gateway
        gateway.activate_profile(
            Service.GETCOURSE, self.settings.presets[Service.GETCOURSE].auth_profile
        )
        self._poll_auth()
        self._auth_timer.start()

    def _poll_auth(self):
        if self._closing or self.auth_gateway is None:
            return

        def action():
            self.auth_gateway.poll()
            snapshot = tuple(self.auth_gateway.status(service) for service in Service)
            if snapshot == self._auth_snapshot:
                return
            self.clear_probe_cache()
            presets = dict(self.settings.presets)
            for status in snapshot:
                presets[status.service] = replace(
                    presets[status.service],
                    auth_profile=status.profile if status.connected else None,
                )
            if presets != dict(self.settings.presets):
                self._save_settings(replace(self.settings, presets=presets))
            self._auth_snapshot = snapshot
            self.auth_changed.emit()

        self._command(action)

    def sign_in_account(self, service):
        if self.auth_gateway is not None:
            return self._command(lambda: self.auth_gateway.sign_in(service, self.settings.language))

    def logout_account(self, service):
        def action():
            if self.auth_gateway is None:
                return
            status = self.auth_gateway.status(service)
            if status.profile is None:
                return
            for job in self.repository.list():
                if job.request.options.auth_profile == status.profile and job.state in {
                    JobState.PROBING,
                    JobState.DOWNLOADING,
                    JobState.PROCESSING,
                }:
                    self.scheduler.pause(job.id)
            self.auth_gateway.logout(status.profile)
            self._poll_auth()

        return self._command(action)

    def configure_getcourse(self, url, method, **values):
        def action():
            if self.auth_gateway is None:
                return None
            profile = self.auth_gateway.configure_getcourse(url, method, **values)
            self._poll_auth()
            return profile

        return self._command(action)

    def import_getcourse(self, url):
        def action():
            if self.auth_gateway is None:
                return None
            profile = self.auth_gateway.import_legacy_getcourse(url)
            self._poll_auth()
            return profile

        return self._command(action)

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
            if not self._title_timer.isActive() and not self.executor.naming:
                self._title_timer.start(self.title_interval_ms)

    @Slot()
    def _name_next(self):
        if self._closing or self.executor.naming:
            return
        for job in self.repository.list():
            if (
                job.title is None
                and job.id not in self._titled
                and job.state in {JobState.QUEUED, JobState.PAUSED}
                and self.executor.can_name(job)
            ):
                self._titled.add(job.id)  # one attempt per session; a failure keeps the label
                if self.executor.request_title(job, self._title_ready):
                    return

    def _title_ready(self, identity, title):
        if title and not self._closing:
            try:
                self._command(lambda: self.scheduler.set_title(identity, title))
            except KeyError:
                pass
        if not self._closing:
            self._title_timer.start(self.title_interval_ms)

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
        self._auth_timer.stop()
        self._title_timer.stop()
        if self.auth_gateway is not None:
            self.auth_gateway.close()
        try:
            self.scheduler.shutdown()
        except Exception:
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
