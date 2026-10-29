"""Single-worker queue. All commands/events run on the owning application thread.

Executors must marshal callbacks to that thread (Qt queued signals in T10).
WorkFinished/WorkFailed/WorkStopped are terminal *worker* acknowledgements: the
executor must release network/process resources before delivering them. A stop
request alone never frees the worker slot. Subscribers receive accepted JobEvents;
command state changes use StageChanged after the repository has been updated.
"""
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from clipflow.application.ports import JobRepository
from clipflow.domain.events import (
    JobEvent, StageChanged, ProgressChanged, FilesSaved, RequestsDiscovered,
    SelectionRequired, RateLimitDeferred, WorkFinished, WorkFailed, WorkStopped,
    StopReason, TitleChanged,
)
from clipflow.domain.models import Job, JobState, ParsedLink, Service, TERMINAL_STATES
from clipflow.domain.urls import request_key,source_reference


class Executor(Protocol):
    def start(self, job: Job, on_event: Callable[[JobEvent], None]) -> None: ...
    def stop(self, job_id: str, reason: StopReason) -> None: ...


_STAGES = (JobState.PROBING, JobState.DOWNLOADING, JobState.PROCESSING)
_ACKS = (WorkFinished, WorkFailed, WorkStopped)


class Scheduler:
    def __init__(self, repository: JobRepository, executor: Executor, *, clock=None):
        self.repository = repository
        self.executor = executor
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._instagram_deferred: RateLimitDeferred | None = None
        self._preferred_job: str | None = None
        self._running = False
        self._drained = False
        self._closed = False
        self._pumping = False
        self._active: tuple[str, str] | None = None
        self._launched = False
        self._discovered = False
        self._stopping = False
        self._subscribers: list[Callable[[JobEvent], None]] = []

    def subscribe(self, callback: Callable[[JobEvent], None]) -> Callable[[], None]:
        self._subscribers.append(callback)

        def unsubscribe():
            if callback in self._subscribers:
                self._subscribers.remove(callback)

        return unsubscribe

    def _publish(self, event: JobEvent) -> None:
        for callback in tuple(self._subscribers):
            callback(event)

    def _save(self, job: Job) -> None:
        self.repository.update(job)
        self._publish(JobEvent(job.id, job.attempt_id or '', StageChanged(job.state)))

    def start(self, job_id: str | None = None) -> None:
        if self._closed:
            raise ValueError('Scheduler is shut down')
        if job_id is not None:
            selected=self.repository.get(job_id)
            if selected.state!=JobState.QUEUED or selected.source_required:
                raise ValueError('Job cannot be started')
            self._preferred_job=job_id
        self._running = True
        self._drained = False
        self._pump()

    def _pump(self) -> None:
        # Synchronous executors may finish inside start(): loop, never recurse.
        if self._pumping:
            return
        self._pumping = True
        try:
            while self._running and not self._drained and self._active is None:
                self._defer_waiting_instagram()
                jobs=self.repository.list()
                queued=[j for j in jobs if j.state==JobState.QUEUED and not j.source_required]
                if not queued:
                    self._drained=not any(j.state==JobState.PAUSED and j.automatic_retry
                                          and j.pause_reason in {'rate_limit','rate_spacing'}
                                          and j.next_allowed_at is not None for j in jobs)
                    break
                if not getattr(self.executor,'is_idle',True): break
                job=next((j for j in queued if j.id==self._preferred_job),queued[0])
                self._preferred_job=None
                job = replace(job, state=JobState.PROBING, attempt_id=uuid4().hex,
                              error=None, pause_reason=None, next_allowed_at=None, automatic_retry=False)
                self._active = (job.id, job.attempt_id)
                self._launched = False
                self._discovered = False
                self._stopping = False
                self._save(job)
                # A subscriber can pause/cancel/shut down while seeing PROBING.
                if self._active != (job.id, job.attempt_id):
                    continue
                self._launched = True
                try:
                    self.executor.start(job, self.handle)
                except Exception:
                    # Do not leak arbitrary adapter exceptions (may contain secrets).
                    self.handle(JobEvent(job.id, job.attempt_id, WorkFailed('worker_start_failed')))
        finally:
            self._pumping = False

    def _stop(self, job_id: str, reason: StopReason) -> None:
        if self._active and self._active[0] == job_id and not self._stopping:
            if not self._launched:
                self._active = None
                return
            self._stopping = True
            # If stop raises, keep the slot occupied: worker teardown is unproven.
            self.executor.stop(job_id, reason)

    def pause(self, job_id: str) -> None:
        job = self.repository.get(job_id)
        if job.state in TERMINAL_STATES:
            return
        if job.state == JobState.PAUSED:
            if job.automatic_retry:
                self._save(replace(job,pause_reason='user',automatic_retry=False))
            return
        self._save(replace(job, state=JobState.PAUSED, pause_reason='user',automatic_retry=False))
        self._stop(job_id, 'pause')

    def resume(self, job_id: str) -> None:
        job = self.repository.get(job_id)
        if job.source_required:
            raise ValueError('Job source must be provided again')
        if job.state != JobState.PAUSED or job.pause_reason == 'selection_required':
            raise ValueError('Job cannot be resumed')
        if job.next_allowed_at and job.next_allowed_at > self.clock():
            raise ValueError('Cooldown has not expired')
        self._save(replace(job, state=JobState.QUEUED, pause_reason=None, next_allowed_at=None))
        self._drained=False
        self._pump()

    def tick(self) -> None:
        """Called on the owner thread by T10; construction never resumes network."""
        if not self._running or self._closed:
            return
        for job in self.repository.list():
            if (job.state == JobState.PAUSED and job.automatic_retry and job.pause_reason in {'rate_limit','rate_spacing'}
                    and job.next_allowed_at and job.next_allowed_at <= self.clock()):
                self._save(replace(job,state=JobState.QUEUED,pause_reason=None,next_allowed_at=None))
        self._pump()

    def _defer_waiting_instagram(self) -> None:
        limit=self._instagram_deferred
        if limit is None or limit.next_allowed_at <= self.clock():
            return
        for waiting in self.repository.list():
            if waiting.state == JobState.QUEUED and waiting.request.link.service == Service.INSTAGRAM:
                self._save(replace(waiting,state=JobState.PAUSED,pause_reason=limit.reason,
                                   next_allowed_at=limit.next_allowed_at,automatic_retry=limit.automatic_retry))

    def cancel(self, job_id: str, include_children: bool = True) -> None:
        targets = {job_id}
        self.repository.get(job_id)
        if include_children:
            while True:
                expanded = targets | {j.id for j in self.repository.list() if j.parent_id in targets}
                if expanded == targets:
                    break
                targets = expanded
        # Persist the whole subtree before stop(), which may acknowledge inline.
        for job in self.repository.list():
            if job.id in targets and job.state not in TERMINAL_STATES:
                self._save(replace(job, state=JobState.CANCELLED, pause_reason=None,
                                   next_allowed_at=None))
        if self._active and self._active[0] in targets:
            self._stop(self._active[0], 'cancel')

    def retry(self, job_id: str) -> None:
        job = self.repository.get(job_id)
        if job.source_required:
            raise ValueError('Job source must be provided again')
        if job.state not in TERMINAL_STATES:
            raise ValueError('Only terminal jobs can be retried')
        self._save(replace(job, state=JobState.QUEUED, error=None,
                           pause_reason=None, next_allowed_at=None))
        self._drained=False
        self._pump()

    def provide_source(self, job_id: str, link: ParsedLink) -> None:
        """Explicit replacement for a source whose secret URL was not persisted."""
        job=self.repository.get(job_id)
        if (not job.source_required or job.state not in TERMINAL_STATES | {JobState.PAUSED}
                or link.service!=job.request.link.service or link.kind!=job.request.link.kind):
            raise ValueError('Job is not waiting for this source')
        if job.request.link.canonical_id!=source_reference(link):
            raise ValueError('Source changed; add it as a new job')
        request=replace(job.request,link=link)
        self._save(replace(job,request=request,state=JobState.PAUSED,source_required=False,
                           pause_reason='user',error=None,automatic_retry=False))

    def select_items(self, job_id: str, ids: tuple[str, ...]) -> None:
        job = self.repository.get(job_id)
        if job.source_required:
            raise ValueError('Job source must be provided again')
        if job.state != JobState.PAUSED or job.pause_reason != 'selection_required' or not ids:
            raise ValueError('Job is not waiting for a nonempty selection')
        updated = replace(job.request, selection=ids)
        self._save(replace(job, request=updated, state=JobState.QUEUED, pause_reason=None))
        self._drained=False
        self._pump()

    def refresh_selection(self, job_id: str) -> None:
        """Explicitly refresh non-persisted material choices after a restart."""
        job=self.repository.get(job_id)
        if job.source_required or job.state!=JobState.PAUSED or job.pause_reason!='selection_required':
            raise ValueError('Job is not waiting for selection')
        self._save(replace(job,state=JobState.QUEUED,pause_reason=None))
        self._drained=False
        self._pump()

    def shutdown(self) -> None:
        self._closed = True
        self._running = False  # Must precede stop(): synchronous ack cannot start next.
        if self._active:
            job = self.repository.get(self._active[0])
            if job.state not in TERMINAL_STATES:
                self._save(replace(job, state=JobState.PAUSED, pause_reason='shutdown'))
            self._stop(job.id, 'shutdown')

    def clear_queue(self) -> tuple[str, ...]:
        self._running=False
        identities=tuple(j.id for j in self.repository.list() if j.state not in TERMINAL_STATES)
        for identity in identities: self.cancel(identity)
        return identities

    def handle(self, event: JobEvent) -> None:
        if (event.job_id, event.attempt_id) != self._active:
            return
        job = self.repository.get(event.job_id)
        payload = event.payload
        if self._stopping:
            if isinstance(payload, _ACKS):
                self._active = None
                self._stopping = False
                self._pump()
            return
        if isinstance(payload, StageChanged):
            if payload.state not in _STAGES or _STAGES.index(payload.state) < _STAGES.index(job.state):
                return
            self.repository.update(replace(job, state=payload.state))
        elif isinstance(payload, FilesSaved):
            self.repository.update(replace(job, result_files=tuple(dict.fromkeys(job.result_files + payload.files))))
        elif isinstance(payload, RequestsDiscovered):
            self._discovered = self._discovered or bool(payload.requests)
            keys = {request_key(j.request) for j in self.repository.list()}
            for request in payload.requests:
                key = request_key(request)
                if key not in keys:
                    self.repository.add(Job(uuid4().hex, request, parent_id=job.id))
                    keys.add(key)
        elif isinstance(payload, SelectionRequired):
            self._save(replace(job, state=JobState.PAUSED, pause_reason='selection_required'))
            self._stop(job.id, 'pause')
        elif isinstance(payload, RateLimitDeferred):
            self._instagram_deferred=payload
            self._save(replace(job, state=JobState.PAUSED, pause_reason=payload.reason,
                               next_allowed_at=payload.next_allowed_at, automatic_retry=payload.automatic_retry))
            self._defer_waiting_instagram()
            self._stop(job.id, 'pause')
        elif isinstance(payload, _ACKS):
            self._active = None
            if isinstance(payload, WorkFinished):
                has_output = (bool(job.result_files) or self._discovered
                              or any(j.parent_id == job.id for j in self.repository.list()))
                updated = replace(job, state=JobState.COMPLETED if has_output else JobState.FAILED,
                                  error=None if has_output else 'no_output')
            elif isinstance(payload, WorkFailed):
                updated = replace(job, state=JobState.FAILED, error=payload.error)
            else:
                updated = replace(job, state=JobState.PAUSED, pause_reason='worker_stopped')
            self._save(updated)
        elif not isinstance(payload, (ProgressChanged,TitleChanged)):
            return
        self._publish(event)
        self._pump()
