"""Network-free mixed batch preview. Only an explicit confirmation submits it."""

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
)

from clipflow.domain.models import ContentKind
from clipflow.domain.urls import request_key
from clipflow.ui.composer import NAMES
from clipflow.ui.i18n import Translator


class PreviewModel(QAbstractTableModel):
    def __init__(self, parent=None, existing_keys=(), translator=None):
        super().__init__(parent)
        self.rows = ()
        self.existing_keys = frozenset(existing_keys)
        self.tr = translator or Translator(parent=self)

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 4

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return (
                self.tr.text('service'),
                self.tr.text('material'),
                self.tr.text('parameters'),
                self.tr.text('folder'),
            )[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if index.isValid() and role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            return self.rows[index.row()][index.column()]
        return None

    def set_preview(self, preview):
        rows = []
        for request in preview.requests:
            link = request.link
            options = request.options
            name = (
                '@' + link.canonical_id
                if link.kind == ContentKind.PROFILE
                else self.tr.text('lesson_video')
                if link.service.value == 'getcourse'
                else link.canonical_id
            )
            if request_key(request) in self.existing_keys:
                name += ' · ' + self.tr.text('already_listed')
            details = [
                options.format.upper(),
                self.tr.text('quality_cap', height=options.max_height)
                if options.max_height
                else self.tr.text('best_quality'),
            ]
            if options.format == 'mp3':
                details = ['MP3', self.tr.text('best_audio')]
            if link.service.value == 'instagram' and options.media_filter == 'photo':
                details = [self.tr.text('photo'), self.tr.text('original_format')]
            if link.service.value == 'instagram':
                details.append(
                    self.tr.text(
                        {'all': 'all_media', 'photo': 'photo_only', 'video': 'video_only'}[
                            options.media_filter
                        ]
                    )
                )
                if options.author_folder:
                    details.append(self.tr.text('author_folder'))
                if options.post_folder:
                    details.append(self.tr.text('post_folder'))
                if options.description:
                    details.append(self.tr.text('description', format=options.description.upper()))
            if link.kind == ContentKind.PROFILE:
                details.append(
                    self.tr.text('latest_count', count=request.profile_limit)
                    if request.profile_limit is not None
                    else self.tr.text('all_posts')
                )
            rows.append((NAMES[link.service], name, ' · '.join(details), str(options.folder)))
        self.beginResetModel()
        self.rows = tuple(rows)
        self.endResetModel()


class BatchDialog(QDialog):
    confirmed = Signal(object)

    def __init__(
        self,
        submission,
        presets,
        profile_limit=10,
        parent=None,
        *,
        existing_keys=(),
        translator=None,
    ):
        super().__init__(parent)
        self.submission = submission
        self.presets = dict(presets)
        self.confirmed_preview = None
        self.tr = translator or Translator(parent=self)
        self.existing_keys = frozenset(existing_keys)
        self.setWindowTitle(self.tr.text('batch'))
        self.resize(780, 600)
        self.setMinimumSize(600, 440)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)
        title = self.tr.widget(QLabel, 'batch_title')
        title.setStyleSheet('font-size: 21px; font-weight: 600;')
        layout.addWidget(title)
        layout.addWidget(self.tr.widget(QLabel, 'batch_help'))
        self.text_input = QPlainTextEdit()
        self.text_input.setPlaceholderText(
            'https://www.youtube.com/watch?v=…\nhttps://www.instagram.com/username/'
        )
        self.text_input.setMinimumHeight(110)
        layout.addWidget(self.text_input, 1)
        profile = QHBoxLayout()
        profile.addWidget(self.tr.widget(QLabel, 'for_profiles'))
        self.limit_box = QComboBox()
        for label, value in [
            (self.tr.text('last_10'), 10),
            (self.tr.text('last_50'), 50),
            (self.tr.text('all_available'), None),
        ]:
            self.limit_box.addItem(label, value)
        self.limit_box.setCurrentIndex(self.limit_box.findData(profile_limit))
        profile.addWidget(self.limit_box)
        profile.addStretch()
        layout.addLayout(profile)
        self.summary = QLabel()
        layout.addWidget(self.summary)
        self.table = QTableView()
        self.model = PreviewModel(self, self.existing_keys, self.tr)
        self.table.setModel(self.model)
        self.table.setWordWrap(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(0, 90)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(1, 150)
        self.table.verticalHeader().hide()
        layout.addWidget(self.table, 1)
        self.issues = QPlainTextEdit()
        self.issues.setReadOnly(True)
        self.issues.setMaximumHeight(70)
        layout.addWidget(self.issues)
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.cancel_button = self.tr.widget(QPushButton, 'cancel')
        self.accept_button = self.tr.widget(QPushButton, 'add')
        self.accept_button.setObjectName('primary')
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.accept_button)
        layout.addLayout(buttons)
        self.text_input.textChanged.connect(self._refresh)
        self.limit_box.currentIndexChanged.connect(self._refresh)
        self.cancel_button.clicked.connect(self.reject)
        self.accept_button.clicked.connect(self._confirm)
        self._refresh()
        self.tr.bind(self, 'batch', setter='setWindowTitle')
        self.tr.changed.connect(self.retranslate)

    def retranslate(self):
        for index, key in enumerate(('last_10', 'last_50', 'all_available')):
            self.limit_box.setItemText(index, self.tr.text(key))
        self._refresh()
        self.model.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, 3)

    def preview(self):
        return self.submission.preview(
            self.text_input.toPlainText(), self.presets, 'batch', self.limit_box.currentData()
        )

    def _refresh(self):
        preview = self.preview()
        self.model.set_preview(preview)
        existing = sum(request_key(request) in self.existing_keys for request in preview.requests)
        self.summary.setText(
            self.tr.text(
                'batch_summary',
                ready=len(preview.requests),
                invalid=len(preview.invalid),
                duplicates=len(preview.duplicate_lines),
                existing=existing,
            )
        )
        issues = [self.tr.text('bad_line', line=error.line) for error in preview.invalid]
        issues.extend(self.tr.text('duplicate_line', line=line) for line in preview.duplicate_lines)
        self.issues.setPlainText('\n'.join(issues))
        self.issues.setVisible(bool(issues))
        self.accept_button.setEnabled(bool(preview.requests))

    def _confirm(self):
        preview = self.preview()
        if preview.requests:
            self.confirmed_preview = preview
            self.confirmed.emit(preview)

    def accept(self):
        if self.confirmed_preview is not None:
            super().accept()
