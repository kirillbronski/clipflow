"""Removing jobs from the list and, only on confirmation, their recorded files."""

from clipflow.application.history import (
    HistoryError,
    deletion_paths,
    prune_empty_folders,
    removable_targets,
)
from clipflow.domain.models import TERMINAL_STATES


class ClearingController:
    """Clearing waits for workers to stop; it then removes what is no longer needed."""

    def __init__(self, presenter):
        self.presenter = presenter
        self._pending = set()
        self._delete_ids = set()

    @property
    def _repository(self):
        return self.presenter.repository

    @property
    def _idle(self):
        return self.presenter.executor.is_idle

    def remove_jobs(self, identities):
        jobs = tuple(self._repository.get(identity) for identity in identities)
        if not self._idle or any(j.state not in TERMINAL_STATES for j in jobs):
            raise HistoryError('job_busy')
        self._repository.remove(identities)
        self.presenter._reload_jobs()

    def clear_history(self):
        if not self._idle:
            raise HistoryError('job_busy')
        self._repository.clear_history()
        self.presenter._reload_jobs()

    def clear_queue(self):
        self._pending.update(self.presenter.scheduler.clear_queue())
        self.flush()

    def clear_all(self, delete_files):
        identities = {job.id for job in self._repository.list()}
        if not identities:
            return
        self._pending.update(identities)
        # A later confirmation applies only to its own target snapshot.
        # In particular an unchecked dialog revokes deletion for those IDs.
        self._delete_ids.difference_update(identities)
        if delete_files:
            self._delete_ids.update(identities)
        self.presenter.scheduler.clear_queue()
        self.flush()

    def flush(self):
        if not self._pending or not self._idle:
            return
        jobs = self._repository.list()
        targets = removable_targets(jobs, self._pending)
        delete_ids = targets & self._delete_ids
        # Never retry destructive IO on the periodic tick after an error.
        self._pending.clear()
        self._delete_ids = set()
        if delete_ids:
            selected = tuple(job for job in jobs if job.id in delete_ids)
            paths = deletion_paths(selected, jobs)
            try:
                self._unlink(paths)
            except HistoryError:
                self.presenter._reload_jobs()
                raise
            prune_empty_folders(selected)
        self._repository.remove(tuple(targets))
        self.presenter._reload_jobs()

    def delete_files(self, job_ids):
        if not self._idle:
            raise HistoryError('job_busy')
        jobs = tuple(self._repository.get(identity) for identity in job_ids)
        paths = deletion_paths(jobs, self._repository.list())
        try:
            self._unlink(paths)
            prune_empty_folders(jobs)
        finally:
            self.presenter._reload_jobs()

    @staticmethod
    def _unlink(paths):
        try:
            for path in paths:
                path.unlink(missing_ok=True)
        except OSError:
            raise HistoryError('file_delete_failed') from None
