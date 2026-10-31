"""The queue: count and bulk buttons, status tabs, the job list and its empty state."""

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
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
from clipflow.ui.job_status import group_details
from clipflow.ui.queue_delegate import QueueDelegate
from clipflow.ui.queue_model import JobListModel, QueueFilter

_HISTORY_STATES = {JobState.COMPLETED, JobState.CANCELLED, JobState.FAILED}
STATUSES = ('all', 'active', 'completed', 'failed')


class QueueView(QListView):
    """Return/Enter activate once on both platforms; keep native navigation."""

    escaped = Signal()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.escaped.emit()
            event.accept()
        elif event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter} and event.modifiers() in {
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
        layout.addWidget(self._group_bar())
        layout.addWidget(self._queue_view(theme), 1)
        self.group_id = None
        self._list_place = None  # scroll and current job of the main list while a group is open
        presenter.jobs_changed.connect(self._group_check)
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

    def _group_bar(self):
        self.group_bar = QWidget()
        bar = QHBoxLayout(self.group_bar)
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(12)
        self.back_button = self.tr.widget(QPushButton, 'group_back')
        self.back_button.clicked.connect(self.close_group)
        bar.addWidget(self.back_button)
        self.group_title = QLabel()
        self.group_title.setStyleSheet('font-weight: 600;')
        bar.addWidget(self.group_title)
        self.group_details = QLabel()
        self.group_details.setObjectName('muted')
        bar.addWidget(self.group_details)
        bar.addStretch()
        self.group_bar.hide()
        return self.group_bar

    def _activate(self, index):
        if index.data(JobListModel.GroupRole) is not None:
            self.open_group(index.data(JobListModel.JobIdRole))
        else:
            self.presenter.toggle_job(index.data(JobListModel.JobIdRole))

    def open_group(self, group_id):
        """Show one playlist or profile in place of the list; the list's place is kept."""
        if self.group_id is None:
            current = self.queue_view.currentIndex()
            self._list_place = (
                self.queue_view.verticalScrollBar().value(),
                current.data(JobListModel.JobIdRole) if current.isValid() else None,
            )
        self.group_id = group_id
        self.proxy.show_group(group_id)
        self.queue_view.scrollToTop()
        self.group_bar.show()
        self._group_header()
        self.status_changed.emit(self.proxy.status)

    def close_group(self):
        if self.group_id is None:
            return
        self.group_id = None
        self.proxy.show_group(None)
        self.group_bar.hide()
        scroll, current = self._list_place or (0, None)
        self._list_place = None
        model = self.presenter.model
        row = model._rows.get(current)
        if row is not None:
            index = self.proxy.mapFromSource(model.index(row))
            if index.isValid():
                self.queue_view.setCurrentIndex(index)
        # The view lays rows out later; restore the scroll once it has.
        QTimer.singleShot(0, self, lambda: self.queue_view.verticalScrollBar().setValue(scroll))
        self.status_changed.emit(self.proxy.status)

    def _group_header(self):
        model = self.presenter.model
        row = model._rows.get(self.group_id)
        if row is None:
            return
        index = model.index(row)
        self.group_title.setText(index.data(JobListModel.TitleRole))
        summary = index.data(JobListModel.GroupRole)
        self.group_details.setText(group_details(summary, self.tr) if summary else '')

    def _group_check(self):
        """Leave a group's screen once the group is gone; otherwise refresh its header."""
        if self.group_id is None:
            return
        if self.group_id not in self.presenter.model._rows:
            self.close_group()
        else:
            self._group_header()

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
        view.activated.connect(self._activate)
        view.escaped.connect(self.close_group)
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
        for status, button in self.status_buttons.items():
            button.setText(self.tr.text('filter_' + status) + '  ' + str(self.proxy.count(status)))
