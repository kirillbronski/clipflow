"""Main-window helpers: a provider that holds a job open, adding and batch input."""

from threading import Event, get_ident

from PySide6.QtCore import Qt

from clipflow.domain.events import (
    ProgressChanged,
    StageChanged,
    TitleChanged,
)
from clipflow.domain.models import (
    JobState,
)
from clipflow.providers.base import DownloadResult
from clipflow.ui.batch_dialog import BatchDialog


class HeldProvider:
    def __init__(self):
        self.started = Event()
        self.released = Event()
        self.torn_down = Event()
        self.thread = None

    def execute(self, request, context):
        self.thread = get_ident()
        self.started.set()
        try:
            context.emit(TitleChanged('Настоящее название'))
            context.emit(StageChanged(JobState.DOWNLOADING))
            context.emit(ProgressChanged(25, 100))
            while not self.released.is_set():
                if context.cancel.wait(0.005):
                    context.cancel.raise_if_cancelled()
            return DownloadResult(())
        finally:
            self.torn_down.set()


def add(window, qtbot, url='https://youtu.be/ABC'):
    window.url_input.setText(url)
    qtbot.mouseClick(window.add_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.presenter.model.rowCount() > 0)
    return window.presenter.model.jobs[0].id


def batch(window, qtbot):
    qtbot.mouseClick(window.batch_button, Qt.MouseButton.LeftButton)
    return next(
        dialog
        for dialog in window._dialogs
        if isinstance(dialog, BatchDialog) and dialog.isVisible()
    )
