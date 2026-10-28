"""Per-service drafts/options and explicit, nonblocking submission modes."""
from dataclasses import replace
from uuid import uuid4

from PySide6.QtCore import Qt,QTimer,Signal
from PySide6.QtWidgets import (
    QFrame,QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QPushButton,QToolButton,
    QLineEdit,QComboBox,QCheckBox,QFileDialog,QApplication,
)

from clipflow.domain.models import Service,ContentKind
from clipflow.domain.urls import parse_url

NAMES={Service.YOUTUBE:'YouTube',Service.INSTAGRAM:'Instagram',Service.GETCOURSE:'GetCourse'}


class Composer(QFrame):
    submit_requested=Signal(str,str,object)
    probe_requested=Signal(str,str)
    batch_requested=Signal()
    preset_changed=Signal(object,object,object)

    def __init__(self,settings,parent=None):
        super().__init__(parent); self.setObjectName('composer')
        self.service=Service.YOUTUBE; self.mode='single'; self._loading=True
        self._presets=dict(settings.presets); self._profile_limit=settings.profile_limit
        self._drafts={s:'' for s in Service}; self._modes={s:'lesson' if s==Service.GETCOURSE else 'single' for s in Service}
        self._post_preference=True; self._probe_id=''; self.quality_pending=False
        self._timer=QTimer(self); self._timer.setSingleShot(True); self._timer.setInterval(300); self._timer.timeout.connect(self._probe)
        layout=QVBoxLayout(self); layout.setContentsMargins(18,16,18,16); layout.setSpacing(12)
        top=QHBoxLayout(); top.addWidget(QLabel('Сервис'))
        self.service_box=QComboBox()
        for service in Service: self.service_box.addItem(NAMES[service],service.value)
        top.addWidget(self.service_box); top.addStretch(); layout.addLayout(top)
        modes=QHBoxLayout(); self.mode_buttons={}
        for mode in ('single','batch','profile','playlist','lesson'):
            button=QPushButton(); button.setObjectName('mode'); button.setCheckable(mode!='batch'); self.mode_buttons[mode]=button; modes.addWidget(button)
            button.clicked.connect(lambda checked=False,m=mode:self._set_mode(m))
        modes.addStretch(); layout.addLayout(modes)
        self.profile_row=QWidget(); self.profile_row.setObjectName('composerSection'); profile=QHBoxLayout(self.profile_row); profile.setContentsMargins(0,0,0,0)
        profile.addWidget(QLabel('Публикации профиля')); self.limit_box=QComboBox()
        for text,value in [('Последние 10',10),('Последние 50',50),('Все доступные',None)]: self.limit_box.addItem(text,value)
        profile.addWidget(self.limit_box); profile.addStretch(); layout.addWidget(self.profile_row)
        entry=QHBoxLayout(); self.paste_button=QPushButton('Вставить')
        self.url_input=QLineEdit(); self.url_input.setAccessibleName('Ссылка для скачивания'); self.url_input.setMinimumWidth(180)
        self.add_button=QPushButton('↓  Добавить в очередь'); self.add_button.setObjectName('primary'); self.add_button.setMinimumWidth(170)
        entry.addWidget(self.paste_button); entry.addWidget(self.url_input,1); entry.addWidget(self.add_button); layout.addLayout(entry)
        self.hint=QLabel(); self.hint.setObjectName('muted'); self.hint.setWordWrap(True); layout.addWidget(self.hint)
        disclosure=QHBoxLayout(); self.parameters_button=QToolButton(); self.parameters_button.setText('Параметры загрузки')
        self.parameters_button.setCheckable(True); self.parameters_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.parameters_button.setArrowType(Qt.ArrowType.RightArrow); disclosure.addWidget(self.parameters_button)
        self.summary=QLabel(); self.summary.setObjectName('muted'); disclosure.addWidget(self.summary,1); layout.addLayout(disclosure)
        self.parameters=QWidget(); self.parameters.setObjectName('composerSection'); params=QVBoxLayout(self.parameters); params.setContentsMargins(0,0,0,0); params.setSpacing(10)
        grid=QGridLayout(); self.format_box=QComboBox(); self.quality_box=QComboBox(); self.filter_box=QComboBox()
        for text,value in [('MP4','mp4'),('MKV','mkv'),('WebM','webm'),('MP3 — только звук','mp3')]: self.format_box.addItem(text,value)
        for text,value in [('Все фото и видео','all'),('Только видео','video'),('Только фото','photo')]: self.filter_box.addItem(text,value)
        for column,(label,control) in enumerate([('Формат видео',self.format_box),('Качество',self.quality_box),('Содержимое',self.filter_box)]):
            widget=QLabel(label); grid.addWidget(widget,0,column); grid.addWidget(control,1,column)
        self.filter_label=grid.itemAtPosition(0,2).widget(); params.addLayout(grid)
        self.instagram_options=QWidget(); self.instagram_options.setObjectName('composerSection'); ig=QVBoxLayout(self.instagram_options); ig.setContentsMargins(0,0,0,0)
        folders=QHBoxLayout(); self.author_folder=QCheckBox('Папка автора'); self.post_folder=QCheckBox('Папка каждого поста')
        folders.addWidget(self.author_folder); folders.addWidget(self.post_folder); folders.addStretch(); ig.addLayout(folders)
        captions=QHBoxLayout(); self.description=QCheckBox('Описание рядом с файлом'); self.description_format=QComboBox()
        for text,value in [('TXT','txt'),('Markdown','md')]: self.description_format.addItem(text,value)
        captions.addWidget(self.description); captions.addWidget(self.description_format); captions.addStretch(); ig.addLayout(captions)
        params.addWidget(self.instagram_options); self.parameters.hide(); layout.addWidget(self.parameters)
        path=QHBoxLayout(); path.addWidget(QLabel('Папка')); self.folder_input=QLineEdit(); self.folder_input.setMinimumWidth(80)
        self.folder_input.setAccessibleName('Папка загрузок'); self.choose_button=QPushButton('Выбрать…'); self.recent_box=QComboBox()
        self.recent_box.setMaximumWidth(110); path.addWidget(self.folder_input,1); path.addWidget(self.choose_button); path.addWidget(self.recent_box); layout.addLayout(path)
        bottom=QHBoxLayout(); self.profile_note=QLabel(); self.profile_note.setObjectName('muted'); self.profile_note.setWordWrap(True)
        bottom.addWidget(self.profile_note,1); self.auto_start=QCheckBox('Автозапуск'); self.auto_start.setChecked(settings.auto_start); bottom.addWidget(self.auto_start); layout.addLayout(bottom)
        self.parameters_button.toggled.connect(self._expand)
        self.service_box.currentIndexChanged.connect(lambda:self.set_service(Service(self.service_box.currentData())))
        self.url_input.textChanged.connect(self._text_changed); self.url_input.returnPressed.connect(self._submit); self.add_button.clicked.connect(self._submit)
        self.paste_button.clicked.connect(lambda:self.url_input.setText(QApplication.clipboard().text().strip()))
        self.choose_button.clicked.connect(self._choose_folder); self.folder_input.editingFinished.connect(self._options_changed)
        self.recent_box.activated.connect(self._recent)
        for box in (self.format_box,self.quality_box,self.filter_box,self.description_format): box.currentIndexChanged.connect(self._options_changed)
        for box in (self.author_folder,self.post_folder,self.description): box.toggled.connect(self._options_changed)
        self.limit_box.currentIndexChanged.connect(self._options_changed)
        self._load(settings); self._loading=False

    def _expand(self,expanded):
        self.parameters.setVisible(expanded)
        self.parameters_button.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)

    def _load(self,settings=None):
        self._loading=True; options=self._presets[self.service]
        self.service_box.setCurrentIndex(self.service_box.findData(self.service.value))
        self.format_box.setCurrentIndex(self.format_box.findData(options.format)); self._quality((),options.max_height)
        self.filter_box.setCurrentIndex(self.filter_box.findData(options.media_filter)); self.author_folder.setChecked(options.author_folder)
        self._post_preference=options.post_folder; self.post_folder.setChecked(options.post_folder)
        self.description.setChecked(options.description is not None)
        self.description_format.setCurrentIndex(self.description_format.findData(options.description or 'txt'))
        self.folder_input.setText(str(options.folder)); self.limit_box.setCurrentIndex(self.limit_box.findData(self._profile_limit))
        if settings is not None:
            self.recent_box.clear(); self.recent_box.addItem('Недавние',None)
            for folder in settings.recent_folders: self.recent_box.addItem(str(folder),str(folder))
        self._mode_ui(); self._summary(); self._loading=False

    def set_settings(self,settings):
        changed=self._presets[self.service]!=settings.presets[self.service] or self._profile_limit!=settings.profile_limit
        self._presets=dict(settings.presets); self._profile_limit=settings.profile_limit
        if changed: self._load(settings)
        else:
            self.recent_box.blockSignals(True); self.recent_box.clear(); self.recent_box.addItem('Недавние',None)
            for path in settings.recent_folders: self.recent_box.addItem(str(path),str(path))
            self.recent_box.blockSignals(False)

    def set_service(self,service,incoming=None):
        service=Service(service)
        if self._loading: return
        if service==self.service and incoming is None: return
        self.service=service; self.mode=self._modes[service]
        self._load(); self.url_input.blockSignals(True)
        self.url_input.setText(self._drafts[service] if incoming is None else incoming)
        self.url_input.blockSignals(False); self._text_changed(self.url_input.text())

    def _set_mode(self,mode):
        if mode=='batch': self.batch_requested.emit(); return
        self.mode=mode; self._modes[self.service]=mode
        self._loading=True; self._mode_ui(); self._loading=False
        self._invalidate()

    def _mode_ui(self):
        allowed={Service.YOUTUBE:('single','batch','playlist'),Service.INSTAGRAM:('single','batch','profile'),Service.GETCOURSE:('lesson','batch')}[self.service]
        labels={'single':'Один пост' if self.service==Service.INSTAGRAM else 'Одно видео','batch':'Несколько ссылок',
                'profile':'Профиль','playlist':'Плейлист','lesson':'Урок / плеер'}
        for mode,button in self.mode_buttons.items():
            button.setText(labels[mode]); button.setVisible(mode in allowed); button.setChecked(mode==self.mode)
        ig=self.service==Service.INSTAGRAM; profile=ig and self.mode=='profile'
        self.instagram_options.setVisible(ig); self.filter_box.setVisible(ig); self.filter_label.setVisible(ig); self.profile_row.setVisible(profile)
        self.post_folder.setChecked(True if profile else self._post_preference); self.post_folder.setEnabled(not profile)
        self.description_format.setEnabled(self.description.isChecked())
        self.profile_note.setText('Каждый пост — в отдельной папке. Список может потребовать полного обхода профиля.' if profile else '')
        self.url_input.setPlaceholderText('https://www.instagram.com/username/' if profile else 'Вставьте ссылку на видео, публикацию или урок')
        photo_only=ig and self.filter_box.currentData()=='photo'
        self.format_box.setEnabled(not photo_only); self.quality_box.setEnabled(not photo_only and self.format_box.currentData()!='mp3')

    def options(self):
        folder=self.folder_input.text().strip()
        if not folder or '\0' in folder: raise ValueError('invalid_folder')
        return replace(self._presets[self.service],folder=folder,format=self.format_box.currentData(),
                       max_height=None if self.format_box.currentData()=='mp3' else self.quality_box.currentData(),media_filter=self.filter_box.currentData(),
                       author_folder=self.author_folder.isChecked(),
                       post_folder=self._post_preference if self.mode=='profile' else self.post_folder.isChecked(),
                       description=self.description_format.currentData() if self.description.isChecked() else None)

    def _options_changed(self,*args):
        if self._loading: return
        if self.mode!='profile': self._post_preference=self.post_folder.isChecked()
        try: options=self.options()
        except ValueError: self.hint.setText('Проверьте папку загрузок.'); return
        self._presets[self.service]=options; self._profile_limit=self.limit_box.currentData()
        self._loading=True; self._mode_ui(); self._summary(); self._loading=False
        self.preset_changed.emit(self.service,options,self._profile_limit); self._invalidate()

    def _summary(self):
        options=self._presets[self.service]
        if self.service==Service.INSTAGRAM and options.media_filter=='photo':
            self.summary.setText('Фото · Исходный формат'); return
        if options.format=='mp3': self.summary.setText('MP3 · Лучший доступный звук'); return
        quality=f'до {options.max_height}p' if options.max_height else 'Лучшее качество'
        self.summary.setText(f'{options.format.upper()} · {quality}')

    def _text_changed(self,text):
        if self._loading: return
        try: detected=parse_url(text).service
        except ValueError: detected=self.service
        if detected!=self.service:
            self.set_service(detected,incoming=text); return
        self._drafts[self.service]=text; self._invalidate()

    def _invalidate(self):
        self._timer.stop(); self._probe_id=uuid4().hex; self.quality_pending=False
        self.probe_requested.emit('',self._probe_id)
        self._loading=True; self._quality((),self._presets[self.service].max_height); self._loading=False
        try: link=parse_url(self.url_input.text())
        except ValueError: self.hint.clear(); return
        if self.mode=='single' and link.kind in {ContentKind.PROFILE,ContentKind.PLAYLIST}:
            self.hint.setText('Для этой ссылки выберите режим «Профиль».' if link.kind==ContentKind.PROFILE else
                              'Для этой ссылки выберите режим «Плейлист».')
            return
        self.quality_pending=True; self.hint.setText('Проверка доступного качества… Добавление в очередь доступно.')
        self._timer.start()

    def _probe(self): self.probe_requested.emit(self.url_input.text(),self._probe_id)

    def apply_probe(self,request_id,heights,error=''):
        if request_id!=self._probe_id: return
        self.quality_pending=False
        self._loading=True; self._quality(heights,self._presets[self.service].max_height); self._loading=False
        self.hint.setText('Проверка остановлена при запуске загрузки. Добавление в очередь доступно.' if error=='probe_cancelled' else
                          'Проверка временно недоступна. Можно добавить в очередь.' if error else
                          'Выбрано лучшее доступное качество.' if heights else 'Качество определяется для каждого материала при скачивании.')

    def _quality(self,heights,cap):
        self.quality_box.clear(); self.quality_box.addItem('Лучшее доступное',None)
        for height in sorted(set(heights)|({cap} if cap is not None else set()),reverse=True):
            self.quality_box.addItem(f'{height}p' if height in heights else f'До {height}p (предел)',height)
        self.quality_box.setCurrentIndex(max(0,self.quality_box.findData(cap)))

    def _submit(self): self.submit_requested.emit(self.url_input.text(),self.mode,self.limit_box.currentData())

    def accept_input(self,text):
        try: service=parse_url(text).service
        except ValueError: return
        if self._drafts[service]==text:
            self._drafts[service]=''
            if service==self.service and self.url_input.text()==text: self.url_input.clear()

    def _choose_folder(self):
        folder=QFileDialog.getExistingDirectory(self,'Папка загрузок',self.folder_input.text())
        if folder: self.folder_input.setText(folder); self._options_changed()

    def _recent(self,index):
        folder=self.recent_box.itemData(index)
        if folder: self.folder_input.setText(folder); self._options_changed()
