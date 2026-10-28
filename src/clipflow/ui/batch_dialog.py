"""Network-free mixed batch preview. Only an explicit confirmation submits it."""
from PySide6.QtCore import Qt,QAbstractTableModel,QModelIndex,Signal
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPlainTextEdit,QPushButton,QComboBox,QTableView,QHeaderView

from clipflow.domain.models import ContentKind
from clipflow.domain.urls import request_key
from clipflow.ui.composer import NAMES


class PreviewModel(QAbstractTableModel):
    def __init__(self,parent=None,existing_keys=()): super().__init__(parent); self.rows=(); self.existing_keys=frozenset(existing_keys)
    def rowCount(self,parent=QModelIndex()): return 0 if parent.isValid() else len(self.rows)
    def columnCount(self,parent=QModelIndex()): return 0 if parent.isValid() else 4
    def headerData(self,section,orientation,role=Qt.ItemDataRole.DisplayRole):
        if role==Qt.ItemDataRole.DisplayRole and orientation==Qt.Orientation.Horizontal:
            return ('Сервис','Материал','Параметры','Папка')[section]
        return None
    def data(self,index,role=Qt.ItemDataRole.DisplayRole):
        if index.isValid() and role in (Qt.ItemDataRole.DisplayRole,Qt.ItemDataRole.ToolTipRole): return self.rows[index.row()][index.column()]
        return None
    def set_preview(self,preview):
        rows=[]
        for request in preview.requests:
            link=request.link; options=request.options
            name='@'+link.canonical_id if link.kind==ContentKind.PROFILE else 'Урок / видео' if link.service.value=='getcourse' else link.canonical_id
            if request_key(request) in self.existing_keys: name+=' · Уже в списке'
            details=[options.format.upper(),f'до {options.max_height}p' if options.max_height else 'Лучшее качество']
            if options.format=='mp3': details=['MP3','Лучший доступный звук']
            if link.service.value=='instagram' and options.media_filter=='photo': details=['Фото','Исходный формат']
            if link.service.value=='instagram':
                details.append({'all':'Фото и видео','photo':'Только фото','video':'Только видео'}[options.media_filter])
                if options.author_folder: details.append('Папка автора')
                if options.post_folder: details.append('Папка каждого поста')
                if options.description: details.append('Описание '+options.description.upper())
            if link.kind==ContentKind.PROFILE: details.append(f'Последние {request.profile_limit}' if request.profile_limit is not None else 'Все доступные посты')
            rows.append((NAMES[link.service],name,' · '.join(details),str(options.folder)))
        self.beginResetModel(); self.rows=tuple(rows); self.endResetModel()


class BatchDialog(QDialog):
    confirmed=Signal(object)
    def __init__(self,submission,presets,profile_limit=10,parent=None,*,existing_keys=()):
        super().__init__(parent); self.submission=submission; self.presets=dict(presets); self.confirmed_preview=None
        self.existing_keys=frozenset(existing_keys)
        self.setWindowTitle('Несколько ссылок'); self.resize(780,600); self.setMinimumSize(600,440)
        layout=QVBoxLayout(self); layout.setContentsMargins(22,22,22,22); layout.setSpacing(12)
        title=QLabel('Добавить несколько ссылок'); title.setStyleSheet('font-size: 21px; font-weight: 600;'); layout.addWidget(title)
        layout.addWidget(QLabel('Одна ссылка на строку. YouTube, Instagram и GetCourse можно смешивать.'))
        self.text_input=QPlainTextEdit(); self.text_input.setPlaceholderText('https://www.youtube.com/watch?v=…\nhttps://www.instagram.com/username/'); self.text_input.setMinimumHeight(110); layout.addWidget(self.text_input,1)
        profile=QHBoxLayout(); profile.addWidget(QLabel('Для профилей Instagram'))
        self.limit_box=QComboBox()
        for label,value in [('Последние 10',10),('Последние 50',50),('Все доступные',None)]: self.limit_box.addItem(label,value)
        self.limit_box.setCurrentIndex(self.limit_box.findData(profile_limit)); profile.addWidget(self.limit_box); profile.addStretch(); layout.addLayout(profile)
        self.summary=QLabel(); layout.addWidget(self.summary)
        self.table=QTableView(); self.model=PreviewModel(self,self.existing_keys); self.table.setModel(self.model); self.table.setWordWrap(False)
        header=self.table.horizontalHeader(); header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0,QHeaderView.ResizeMode.Fixed); header.resizeSection(0,90)
        header.setSectionResizeMode(1,QHeaderView.ResizeMode.Fixed); header.resizeSection(1,150)
        self.table.verticalHeader().hide(); layout.addWidget(self.table,1)
        self.issues=QPlainTextEdit(); self.issues.setReadOnly(True); self.issues.setMaximumHeight(70); layout.addWidget(self.issues)
        buttons=QHBoxLayout(); buttons.addStretch(); self.cancel_button=QPushButton('Отмена'); self.accept_button=QPushButton('Добавить в очередь'); self.accept_button.setObjectName('primary')
        buttons.addWidget(self.cancel_button); buttons.addWidget(self.accept_button); layout.addLayout(buttons)
        self.text_input.textChanged.connect(self._refresh); self.limit_box.currentIndexChanged.connect(self._refresh)
        self.cancel_button.clicked.connect(self.reject); self.accept_button.clicked.connect(self._confirm); self._refresh()

    def preview(self):
        return self.submission.preview(self.text_input.toPlainText(),self.presets,'batch',self.limit_box.currentData())

    def _refresh(self):
        preview=self.preview(); self.model.set_preview(preview)
        existing=sum(request_key(request) in self.existing_keys for request in preview.requests)
        self.summary.setText(f'Готово: {len(preview.requests)} · Неверных: {len(preview.invalid)} · Повторов: {len(preview.duplicate_lines)} · Уже в списке: {existing}')
        issues=[f'Строка {error.line}: неподдерживаемая или неверная ссылка.' for error in preview.invalid]
        issues.extend(f'Строка {line}: повтор ссылки.' for line in preview.duplicate_lines)
        self.issues.setPlainText('\n'.join(issues)); self.issues.setVisible(bool(issues)); self.accept_button.setEnabled(bool(preview.requests))

    def _confirm(self):
        preview=self.preview()
        if preview.requests:
            self.confirmed_preview=preview; self.confirmed.emit(preview)

    def accept(self):
        if self.confirmed_preview is not None: super().accept()
