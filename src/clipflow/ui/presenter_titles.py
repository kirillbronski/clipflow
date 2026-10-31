"""Background naming: one metadata lookup at a time, paced to stay polite to the site."""

import contextlib

from PySide6.QtCore import QObject, QTimer, Slot

from clipflow.domain.models import JobState

_WAITING = {JobState.QUEUED, JobState.PAUSED}


class TitleNamer(QObject):
    """Names waiting jobs ahead of their download; the pace is the presenter's interval."""

    def __init__(self, presenter):
        super().__init__(presenter)
        self.presenter = presenter
        self._titled = set()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._name_next)

    def schedule(self):
        if not self._timer.isActive() and not self.presenter.executor.naming:
            self._start()

    def stop(self):
        self._timer.stop()

    def _start(self):
        self._timer.start(self.presenter.title_interval_ms)

    @Slot()
    def _name_next(self):
        presenter = self.presenter
        executor = presenter.executor
        if presenter._closing or executor.naming:
            return
        for job in presenter.repository.list():
            if (
                job.title is None
                and job.id not in self._titled
                and job.state in _WAITING
                and executor.can_name(job)
            ):
                self._titled.add(job.id)  # one attempt per session; a failure keeps the label
                if executor.request_title(job, self._ready):
                    return

    def _ready(self, identity, title):
        presenter = self.presenter
        if title and not presenter._closing:
            with contextlib.suppress(KeyError):
                presenter._command(lambda: presenter.scheduler.set_title(identity, title))
        if not presenter._closing:
            self._start()
