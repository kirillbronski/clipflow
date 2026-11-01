"""The line above the queue, as in 4K: kind tabs, status menu, item count, search, sorting."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton, QWidget

from clipflow.application.queue_view import plural
from clipflow.ui.queue_model import KINDS, SORTS

STATUSES = ('all', 'active', 'completed', 'failed')
_KIND_KEYS = {
    'all': 'kind.all',
    'video': 'kind.video',
    'audio': 'kind.audio',
    'photo': 'kind.photo',
    'playlists': 'kind.playlists',
}
_STATUS_KEYS = {
    'all': 'filter_all',
    'active': 'filter_active',
    'completed': 'filter_completed',
    'failed': 'filter_failed',
}
_SORT_KEYS = {
    'added': 'sort.added',
    'title': 'sort.title',
    'size': 'sort.size',
    'duration': 'sort.duration',
}
_ITEM_KEYS = {'one': 'items_one', 'few': 'items_few', 'many': 'items_many'}


class _SearchField(QLineEdit):
    escaped = Signal()
    left = Signal()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.escaped.emit()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.left.emit()


class QueueToolbar(QWidget):
    kind_changed = Signal(str)
    status_changed = Signal(str)
    query_changed = Signal(str)
    sort_changed = Signal(str, bool)

    def __init__(self, translator, parent=None):
        super().__init__(parent)
        self.tr = translator
        self.status = 'all'
        self._counts = dict.fromkeys(STATUSES, 0)
        self._visible = 0
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        self.kind_buttons = {}
        for kind in KINDS:
            button = QPushButton()
            button.setObjectName('statusTab')
            button.setCheckable(True)
            button.setChecked(kind == 'all')
            button.clicked.connect(lambda checked=False, k=kind: self._pick_kind(k))
            layout.addWidget(button)
            self.kind_buttons[kind] = button
        layout.addStretch(1)
        self.status_button = QPushButton()
        self.status_button.setObjectName('statusTab')
        self.status_menu = QMenu(self)
        group = QActionGroup(self)
        self.status_actions = {}
        for status in STATUSES:
            action = QAction(self)
            action.setCheckable(True)
            action.setChecked(status == 'all')
            action.triggered.connect(lambda checked=False, s=status: self._pick_status(s))
            group.addAction(action)
            self.status_menu.addAction(action)
            self.status_actions[status] = action
        self.status_button.setMenu(self.status_menu)
        layout.addWidget(self.status_button)
        self.items_label = QLabel()
        self.items_label.setObjectName('muted')
        layout.addWidget(self.items_label)
        self.search_field = _SearchField()
        self.search_field.setClearButtonEnabled(True)
        self.search_field.setMinimumWidth(180)
        self.search_field.hide()
        self.search_field.textChanged.connect(self._query)
        self.search_field.escaped.connect(self._escape)
        self.search_field.left.connect(lambda: self.close_search(only_if_empty=True))
        layout.addWidget(self.search_field)
        self.search_button = QPushButton('🔍')
        self.search_button.setObjectName('statusTab')
        self.search_button.clicked.connect(self.open_search)
        layout.addWidget(self.search_button)
        self.sort_button = QPushButton('⇅')
        self.sort_button.setObjectName('statusTab')
        self.sort_menu = QMenu(self)
        group = QActionGroup(self)
        self.sort_actions = {}
        for key in SORTS:
            action = QAction(self)
            action.setCheckable(True)
            action.setChecked(key == 'added')
            action.triggered.connect(self._sort)
            group.addAction(action)
            self.sort_menu.addAction(action)
            self.sort_actions[key] = action
        self.sort_menu.addSeparator()
        self.descending_action = QAction(self)
        self.descending_action.setCheckable(True)
        self.descending_action.triggered.connect(self._sort)
        self.sort_menu.addAction(self.descending_action)
        self.sort_menu.addSeparator()
        self.note_action = QAction(self)
        self.note_action.setEnabled(False)
        self.sort_menu.addAction(self.note_action)
        self.sort_button.setMenu(self.sort_menu)
        layout.addWidget(self.sort_button)
        self.tr.changed.connect(self.refresh)
        self.refresh()

    @property
    def sort_key(self):
        return next(key for key, action in self.sort_actions.items() if action.isChecked())

    def refresh(self):
        for kind, button in self.kind_buttons.items():
            button.setText(self.tr.text(_KIND_KEYS[kind]))
        for status, action in self.status_actions.items():
            action.setText(f'{self.tr.text(_STATUS_KEYS[status])}  {self._counts[status]}')
        self.status_button.setText(self.status_actions[self.status].text() + ' ▾')
        for key, action in self.sort_actions.items():
            action.setText(self.tr.text(_SORT_KEYS[key]))
        self.descending_action.setText(self.tr.text('sort.descending'))
        self.note_action.setText(self.tr.text('sort.note'))
        self.search_field.setPlaceholderText(self.tr.text('search_hint'))
        form = plural(self._visible, self.tr.language)
        self.items_label.setText(self.tr.text(_ITEM_KEYS[form], count=self._visible))

    def set_counts(self, counts):
        self._counts = {status: counts.get(status, 0) for status in STATUSES}
        self.refresh()

    def set_visible_count(self, count):
        self._visible = count
        self.refresh()

    def open_search(self):
        self.search_field.show()
        self.search_field.setFocus()

    def close_search(self, only_if_empty=False):
        if only_if_empty and self.search_field.text():
            return
        self.search_field.clear()
        self.search_field.hide()

    def _escape(self):
        self.close_search()
        self.search_button.setFocus()

    def _pick_kind(self, kind):
        for name, button in self.kind_buttons.items():
            button.setChecked(name == kind)
        self.kind_changed.emit(kind)

    def _pick_status(self, status):
        self.status = status
        self.status_actions[status].setChecked(True)
        self.refresh()
        self.status_changed.emit(status)

    def _query(self, text):
        _highlight(self.search_button, bool(text.strip()))
        self.query_changed.emit(text)

    def _sort(self):
        key = self.sort_key
        descending = self.descending_action.isChecked()
        _highlight(self.sort_button, key != 'added' or descending)
        self.sort_changed.emit(key, descending)


def _highlight(button, active):
    button.setProperty('active', active)
    button.style().unpolish(button)
    button.style().polish(button)
