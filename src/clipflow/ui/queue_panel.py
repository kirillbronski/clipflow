"""The queue: count and bulk buttons, status tabs, the job list and its empty state."""

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QBoxLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListView,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from clipflow.domain.models import JobState
from clipflow.ui.queue_delegate import QueueDelegate
from clipflow.ui.queue_model import JobListModel, QueueFilter

_HISTORY_STATES = {JobState.COMPLETED, JobState.CANCELLED, JobState.FAILED}
STATUSES = ('all', 'active', 'completed', 'failed')


class QueueView(QListView):
    """Return/Enter activate once on both platforms; keep native navigation."""

    def keyPressEvent(self, event):
        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter} and event.modifiers() in {
            Qt.KeyboardModifier.NoModifier,
            Qt.KeyboardModifier.KeypadModifier,
        }:
            if not event.isAutoRepeat() and self.currentIndex().isValid():
                self.activated.emit(self.currentIndex())
            event.accept()
        else:
            super().keyPressEvent(event)


def _job_word(count):
    """Russian plural form of «задание» for a count."""
    if count % 10 == 1 and count % 100 != 11:
        return 'job_one'
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return 'job_few'
    return 'job_many'


class QueuePanel(QWidget):
    clear_all_requested = Signal()
    row_action = Signal(str, str)
    context_menu = Signal(QPoint)
    status_changed = Signal(str)

    def __init__(self, presenter, theme, translator, parent=None):
        super().__init__(parent)
        self.presenter = presenter
        self.tr = translator
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)
        layout.addWidget(self._toolbar())
        layout.addWidget(self._status_tabs())
        layout.addWidget(self._queue_view(theme), 1)
        self.empty = self.tr.widget(QLabel, 'empty')
        self.empty.setObjectName('muted')
        self.empty.setWordWrap(True)
        layout.addWidget(self.empty)

    def _toolbar(self):
        self.toolbar = QWidget()
        self.toolbar.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.header = QGridLayout(self.toolbar)
        self.header.setContentsMargins(0, 0, 0, 0)
        self.header.setSpacing(8)
        self.header.setColumnStretch(0, 1)
        self.count_label = QLabel()
        self.header.addWidget(self.count_label, 0, 0)
        self.actions = QWidget()
        self.actions_layout = QHBoxLayout(self.actions)
        self.actions_layout.setContentsMargins(0, 0, 0, 0)
        self.actions_layout.setSpacing(8)
        self.start_button = self._action('start_queue', self.presenter.start_queue)
        self.cancel_queue_button = self._action('cancel_queue', self.presenter.cancel_queue)
        self.clear_all_button = self._action('clear_all', self.clear_all_requested.emit)
        # Begin wrapped; the toolbar must never impose a wider window minimum.
        self.header.addWidget(self.actions, 1, 0, 1, 2, Qt.AlignmentFlag.AlignRight)
        self._wrap_state = None
        return self.toolbar

    def _action(self, key, slot):
        button = self.tr.widget(QPushButton, key)
        button.clicked.connect(slot)
        self.actions_layout.addWidget(button)
        return button

    def _status_tabs(self):
        self.status_tabs = QWidget()
        tab_layout = QHBoxLayout(self.status_tabs)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(16)
        self.status_buttons = {}
        for status in STATUSES:
            button = QPushButton()
            button.setObjectName('statusTab')
            button.setCheckable(True)
            button.setChecked(status == 'all')
            button.clicked.connect(lambda checked=False, s=status: self.filter_status(s))
            tab_layout.addWidget(button)
            self.status_buttons[status] = button
        tab_layout.addStretch()
        return self.status_tabs

    def _queue_view(self, theme):
        view = self.queue_view = QueueView()
        view.setObjectName('queue')
        view.setUniformItemSizes(True)
        view.setSpacing(0)
        view.setMinimumHeight(96)
        self.proxy = QueueFilter(self.presenter.model, self)
        view.setModel(self.proxy)
        delegate = QueueDelegate(view, theme=theme, translator=self.tr)
        view.setItemDelegate(delegate)
        delegate.action_requested.connect(self.row_action.emit)
        view.activated.connect(
            lambda index: self.presenter.toggle_job(index.data(JobListModel.JobIdRole))
        )
        view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        view.customContextMenuRequested.connect(self.context_menu.emit)
        return view

    def filter_status(self, status):
        self.proxy.show_status(status)
        for name, button in self.status_buttons.items():
            button.setChecked(name == status)
        self.status_changed.emit(status)

    def arrange(self, available):
        """Wrap the bulk buttons under the count, then stack them, as the width shrinks."""
        buttons = [
            b
            for b in (self.start_button, self.cancel_queue_button, self.clear_all_button)
            if not b.isHidden()
        ]
        horizontal = sum(max(b.minimumWidth(), b.minimumSizeHint().width()) for b in buttons)
        horizontal += 8 * max(0, len(buttons) - 1)
        count = max(self.count_label.minimumWidth(), self.count_label.minimumSizeHint().width())
        vertical = horizontal > available
        wrapped = vertical or count + horizontal + 8 > available
        state = (wrapped, vertical)
        if state == self._wrap_state:
            return
        self._wrap_state = state
        self.actions_layout.setDirection(
            QBoxLayout.Direction.TopToBottom if vertical else QBoxLayout.Direction.LeftToRight
        )
        self.header.removeWidget(self.actions)
        self.header.addWidget(
            self.actions,
            1 if wrapped else 0,
            0 if wrapped else 1,
            1,
            2 if wrapped else 1,
            Qt.AlignmentFlag.AlignRight,
        )

    def update_counts(self, downloads):
        """Texts and visibility for the current filter; ``downloads`` is the section shown."""
        count = self.proxy.rowCount()
        self.count_label.setText(
            self.tr.text('history_count', count=count)
            if self.proxy.history
            else self.tr.text('queue_count', count=count, word=self.tr.text(_job_word(count)))
        )
        self.start_button.setVisible(downloads and not self.proxy.history)
        self.cancel_queue_button.setVisible(downloads and not self.proxy.history)
        self.clear_all_button.setVisible(downloads)
        self.empty.setVisible(downloads and count == 0)
        scoped = [j for j in self.presenter.model.jobs if self._in_scope(j)]
        counts = {
            'all': len(scoped),
            'active': sum(j.state not in _HISTORY_STATES for j in scoped),
            'completed': sum(j.state == JobState.COMPLETED for j in scoped),
            'failed': sum(j.state == JobState.FAILED for j in scoped),
        }
        for status, button in self.status_buttons.items():
            button.setText(self.tr.text('filter_' + status) + '  ' + str(counts[status]))

    def _in_scope(self, job):
        service = self.proxy.service
        return (service is None or job.request.link.service.value == service) and (
            not self.proxy.history or job.state in _HISTORY_STATES
        )
