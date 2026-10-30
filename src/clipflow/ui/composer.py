"""Per-service drafts/options and explicit, nonblocking submission modes."""
from dataclasses import replace
from uuid import uuid4

from PySide6.QtCore import Qt,QTimer,Signal
from PySide6.QtGui import QFont,QFontMetrics
from PySide6.QtWidgets import (
    QFrame,QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QPushButton,QToolButton,
    QLineEdit,QComboBox,QCheckBox,QFileDialog,QApplication,
)

from clipflow.domain.models import Service,ContentKind
from clipflow.domain.urls import parse_url
from clipflow.ui.i18n import Translator

NAMES={Service.YOUTUBE:'YouTube',Service.INSTAGRAM:'Instagram',Service.GETCOURSE:'GetCourse'}


class Composer(QFrame):
    submit_requested=Signal(str,str,object)
    probe_requested=Signal(str,str)
    batch_requested=Signal()
    preset_changed=Signal(object,object,object)
    service_changed=Signal(object)
    layout_changed=Signal()

    def __init__(self,settings,parent=None,*,translator=None):
        super().__init__(parent); self.setObjectName('composer')
        self.tr=translator or Translator(settings.language,self); self._heights=(); self._hint_key=None
        self.service=Service.YOUTUBE; self.mode='single'; self._loading=True
        self._presets=dict(settings.presets); self._profile_limit=settings.profile_limit
        self._drafts={s:'' for s in Service}; self._modes={s:'lesson' if s==Service.GETCOURSE else 'single' for s in Service}
        self._post_preference=True; self._probe_id=''; self.quality_pending=False
        self._timer=QTimer(self); self._timer.setSingleShot(True); self._timer.setInterval(300); self._timer.timeout.connect(self._probe)
        layout=QVBoxLayout(self); layout.setContentsMargins(20,16,20,16); layout.setSpacing(10)
        top=QHBoxLayout(); self.download_label=self.tr.widget(QLabel,'download_label'); top.addWidget(self.download_label); top.addStretch()
        self.service_box=QComboBox()
        for service in Service: self.service_box.addItem(NAMES[service],service.value)
        self.service_box.hide()
        modes=QHBoxLayout(); self._modes_layout=modes; modes.setSpacing(4); self.mode_buttons={}
        for mode in ('single','batch','profile','playlist','lesson'):
            button=QPushButton(); button.setObjectName('mode'); button.setCheckable(mode!='batch'); self.mode_buttons[mode]=button; modes.addWidget(button)
            button.clicked.connect(lambda checked=False,m=mode:self._set_mode(m))
        top.addLayout(modes); layout.addLayout(top)
        self.profile_row=QWidget(); self.profile_row.setObjectName('composerSection'); profile=QHBoxLayout(self.profile_row); profile.setContentsMargins(0,0,0,0)
        profile.addWidget(self.tr.widget(QLabel,'profile_posts')); self.limit_box=QComboBox()
        for text,value in [(self.tr.text('last_10'),10),(self.tr.text('last_50'),50),(self.tr.text('all_available'),None)]: self.limit_box.addItem(text,value)
        profile.addWidget(self.limit_box); profile.addStretch(); layout.addWidget(self.profile_row)
        entry=QGridLayout(); self._entry=entry; self.paste_button=self.tr.widget(QPushButton,'paste')
        self.url_input=QLineEdit(); self.url_input.setAccessibleName(self.tr.text('link_accessible')); self.url_input.setMinimumWidth(180)
        self.add_button=self.tr.widget(QPushButton,'add_primary'); self.add_button.setObjectName('primary'); self.add_button.setMinimumWidth(170)
        self.paste_button.setObjectName('inlinePaste')
        input_layout=QHBoxLayout(self.url_input); input_layout.setContentsMargins(0,3,4,3); input_layout.addStretch(); input_layout.addWidget(self.paste_button)
        self.url_input.setTextMargins(0,0,72,0)
        entry.addWidget(self.url_input,0,1); entry.addWidget(self.add_button,0,2); entry.setColumnStretch(1,1); layout.addLayout(entry)
        self.hint=QLabel(); self.hint.setObjectName('muted'); self.hint.setWordWrap(True); layout.addWidget(self.hint)
        disclosure=QHBoxLayout(); self.parameters_button=QToolButton(); self.parameters_button.setText(self.tr.text('download_options'))
        self.parameters_button.setCheckable(True); self.parameters_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.parameters_button.setArrowType(Qt.ArrowType.RightArrow); disclosure.addWidget(self.parameters_button)
        divider=QFrame(); divider.setObjectName('divider'); divider.setFixedHeight(1); layout.addWidget(divider)
        self.summary=QLabel(); self.summary.setWordWrap(True); self.summary.setObjectName('muted'); self.summary.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter); disclosure.addWidget(self.summary,1); layout.addLayout(disclosure)
        self.parameters=QWidget(); self.parameters.setObjectName('composerSection'); params=QVBoxLayout(self.parameters); params.setContentsMargins(0,0,0,0); params.setSpacing(10)
        grid=QGridLayout(); self.format_box=QComboBox(); self.quality_box=QComboBox(); self.filter_box=QComboBox()
        for text,value in [('MP4','mp4'),('MKV','mkv'),('WebM','webm'),(self.tr.text('audio_format'),'mp3')]: self.format_box.addItem(text,value)
        for text,value in [(self.tr.text('all_media'),'all'),(self.tr.text('video_only'),'video'),(self.tr.text('photo_only'),'photo')]: self.filter_box.addItem(text,value)
        for column,(key,control) in enumerate([('video_format',self.format_box),('quality',self.quality_box),('content',self.filter_box)]):
            widget=self.tr.widget(QLabel,key); grid.addWidget(widget,0,column); grid.addWidget(control,1,column)
        self.filter_label=grid.itemAtPosition(0,2).widget(); params.addLayout(grid)
        self.instagram_options=QWidget(); self.instagram_options.setObjectName('composerSection'); ig=QVBoxLayout(self.instagram_options); ig.setContentsMargins(0,0,0,0)
        folders=QHBoxLayout(); self.author_folder=self.tr.widget(QCheckBox,'author_folder'); self.post_folder=self.tr.widget(QCheckBox,'post_folder')
        folders.addWidget(self.author_folder); folders.addWidget(self.post_folder); folders.addStretch(); ig.addLayout(folders)
        captions=QHBoxLayout(); self.description=self.tr.widget(QCheckBox,'description_beside'); self.description_format=QComboBox()
        for text,value in [('TXT','txt'),('Markdown','md')]: self.description_format.addItem(text,value)
        captions.addWidget(self.description); captions.addWidget(self.description_format); captions.addStretch(); ig.addLayout(captions)
        params.addWidget(self.instagram_options); self.parameters.hide(); layout.addWidget(self.parameters)
        path=QHBoxLayout(); path.addWidget(self.tr.widget(QLabel,'folder')); self.folder_input=QLineEdit(); self.folder_input.setMinimumWidth(80)
        self.folder_input.setAccessibleName(self.tr.text('download_folder')); self.choose_button=self.tr.widget(QPushButton,'choose'); self.recent_box=QComboBox()
        self.recent_box.setMaximumWidth(110); path.addWidget(self.folder_input,1); path.addWidget(self.choose_button); path.addWidget(self.recent_box); params.addLayout(path)
        bottom=QHBoxLayout(); self.profile_note=QLabel(); self.profile_note.setObjectName('muted'); self.profile_note.setWordWrap(True)
        bottom.addWidget(self.profile_note,1); self.auto_start=self.tr.widget(QCheckBox,'auto_start'); self.auto_start.setChecked(settings.auto_start); bottom.addWidget(self.auto_start); params.addLayout(bottom)
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
        self.tr.changed.connect(self.retranslate)
        for box in (self.format_box,self.quality_box,self.filter_box):
            box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon); box.setMinimumContentsLength(8)

    def resizeEvent(self,event):
        super().resizeEvent(event); self._arrange_entry()

    def _arrange_entry(self):
        parent=self.parentWidget()
        available=min(self.width(),parent.width() if parent is not None else self.width())
        margins=self.layout().contentsMargins()
        caption_width=max(self.download_label.minimumWidth(),self.download_label.minimumSizeHint().width())
        needed=self._modes_layout.minimumSize().width()+caption_width+16+margins.left()+margins.right()
        self.download_label.setVisible(needed<=available)
        self.add_button.ensurePolished(); self.paste_button.ensurePolished()
        self.add_button.setMinimumWidth(max(170,self.add_button.fontMetrics().horizontalAdvance(self.add_button.text())+24))
        needed=self.url_input.minimumWidth()+self.add_button.minimumWidth()+48
        compact=self.width()<needed
        position=(1,1) if compact else (0,2)
        current=self._entry.getItemPosition(self._entry.indexOf(self.add_button))[:2]
        if position!=current:
            self._entry.removeWidget(self.add_button)
            self._entry.addWidget(self.add_button,*position,Qt.AlignmentFlag.AlignRight)

    def retranslate(self):
        self._loading=True
        self.limit_box.setItemText(0,self.tr.text('last_10')); self.limit_box.setItemText(1,self.tr.text('last_50')); self.limit_box.setItemText(2,self.tr.text('all_available'))
        self.format_box.setItemText(3,self.tr.text('audio_format'))
        for index,key in enumerate(('all_media','video_only','photo_only')): self.filter_box.setItemText(index,self.tr.text(key))
        self.recent_box.setItemText(0,self.tr.text('recent'))
        self.parameters_button.setText(self.tr.text('download_options'))
        self.url_input.setAccessibleName(self.tr.text('link_accessible')); self.folder_input.setAccessibleName(self.tr.text('download_folder'))
        self._quality(self._heights,self.quality_box.currentData()); self._mode_ui(); self._summary()
        if self._hint_key: self.hint.setText(self.tr.text(self._hint_key))
        self._loading=False
        self._arrange_entry()

    def _hint(self,key):
        self._hint_key=key; self.hint.setText(self.tr.text(key) if key else '')
        self.layout_changed.emit()

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
            self.recent_box.clear(); self.recent_box.addItem(self.tr.text('recent'),None)
            for folder in settings.recent_folders: self.recent_box.addItem(str(folder),str(folder))
        self._mode_ui(); self._summary(); self._loading=False

    def set_settings(self,settings):
        changed=self._presets[self.service]!=settings.presets[self.service] or self._profile_limit!=settings.profile_limit
        self._presets=dict(settings.presets); self._profile_limit=settings.profile_limit
        if changed: self._load(settings)
        else:
            self.recent_box.blockSignals(True); self.recent_box.clear(); self.recent_box.addItem(self.tr.text('recent'),None)
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
        self.service_changed.emit(service)

    def _set_mode(self,mode):
        if mode=='batch': self.batch_requested.emit(); return
        self.mode=mode; self._modes[self.service]=mode
        self._loading=True; self._mode_ui(); self._loading=False
        self._invalidate()

    def _mode_ui(self):
        allowed={Service.YOUTUBE:('single','batch','playlist'),Service.INSTAGRAM:('single','batch','profile'),Service.GETCOURSE:('lesson','batch')}[self.service]
        labels={'single':self.tr.text('single_post') if self.service==Service.INSTAGRAM else self.tr.text('single_video'),'batch':self.tr.text('batch'),
                'profile':self.tr.text('profile'),'playlist':self.tr.text('playlist'),'lesson':self.tr.text('lesson_player')}
        for mode,button in self.mode_buttons.items():
            button.setText(labels[mode]); button.setVisible(mode in allowed); button.setChecked(mode==self.mode)
            # Qt's stylesheet size hint uses the unchecked font. Reserve the
            # semibold ink bounds too, so checking a mode cannot clip its text.
            button.ensurePolished()
            font=QFont(button.font()); font.setWeight(QFont.Weight.DemiBold)
            metrics=QFontMetrics(font)
            width=max(metrics.horizontalAdvance(button.text()),metrics.boundingRect(button.text()).width())
            button.setMinimumWidth(width+30)
            button.setMinimumHeight(metrics.height()+20)
        self._arrange_entry()
        ig=self.service==Service.INSTAGRAM; profile=ig and self.mode=='profile'
        self.instagram_options.setVisible(ig); self.filter_box.setVisible(ig); self.filter_label.setVisible(ig); self.profile_row.setVisible(profile)
        self.post_folder.setChecked(True if profile else self._post_preference); self.post_folder.setEnabled(not profile)
        self.description_format.setEnabled(self.description.isChecked())
        self.profile_note.setText(self.tr.text('profile_note') if profile else '')
        self.url_input.setPlaceholderText('https://www.instagram.com/username/' if profile else self.tr.text('instagram_link') if ig else self.tr.text('link_placeholder'))
        if not self.url_input.text(): self._hint('instagram_hint' if ig and not profile else 'youtube_hint' if self.service==Service.YOUTUBE else 'getcourse_hint' if self.service==Service.GETCOURSE else 'profile_note')
        photo_only=ig and self.filter_box.currentData()=='photo'
        music=self._is_music()
        self.format_box.setCurrentIndex(self.format_box.findData('mp3' if music else self._presets[self.service].format))
        self.format_box.setEnabled(not photo_only and not music)
        self.quality_box.setEnabled(not photo_only and self.format_box.currentData()!='mp3')

    def _is_music(self):
        try: return self.service==Service.YOUTUBE and parse_url(self.url_input.text()).is_music
        except ValueError: return False

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
        try: options=self.preset_options()
        except ValueError: self._hint('check_folder'); return
        self._presets[self.service]=options; self._profile_limit=self.limit_box.currentData()
        self._loading=True; self._mode_ui(); self._summary(); self._loading=False
        self.preset_changed.emit(self.service,options,self._profile_limit); self._invalidate()

    def preset_options(self):
        options=self.options()
        if self._is_music():
            previous=self._presets[self.service]
            return replace(options,format=previous.format,max_height=previous.max_height)
        return options

    def _summary(self):
        options=self._presets[self.service]
        if self.service==Service.INSTAGRAM and options.media_filter=='photo':
            self.summary.setText(self.tr.text('photo_summary')); return
        if self._is_music() or options.format=='mp3': self.summary.setText(self.tr.text('audio_summary')); return
        quality=self.tr.text('quality_cap',height=options.max_height) if options.max_height else self.tr.text('best_quality')
        self.summary.setText(f'{options.format.upper()} · {quality}')

    def _text_changed(self,text):
        if self._loading: return
        try: detected=parse_url(text).service
        except ValueError: detected=self.service
        if detected!=self.service:
            self.set_service(detected,incoming=text); return
        self._drafts[self.service]=text
        self._loading=True; self._mode_ui(); self._summary(); self._loading=False
        self._invalidate()

    def _invalidate(self):
        self._timer.stop(); self._probe_id=uuid4().hex; self.quality_pending=False
        self.probe_requested.emit('',self._probe_id)
        self._loading=True; self._quality((),None if self._is_music() else self._presets[self.service].max_height); self._loading=False
        try: link=parse_url(self.url_input.text())
        except ValueError:
            self._hint('instagram_hint' if self.service==Service.INSTAGRAM and self.mode!='profile' else 'youtube_hint' if self.service==Service.YOUTUBE else 'getcourse_hint' if self.service==Service.GETCOURSE else 'profile_note')
            return
        if self.mode=='single' and link.kind in {ContentKind.PROFILE,ContentKind.PLAYLIST}:
            self._hint('choose_profile' if link.kind==ContentKind.PROFILE else 'choose_playlist')
            return
        self.quality_pending=True; self._hint('quality_pending')
        self._timer.start()

    def _probe(self): self.probe_requested.emit(self.url_input.text(),self._probe_id)

    def apply_probe(self,request_id,heights,error=''):
        if request_id!=self._probe_id: return
        self.quality_pending=False
        music=self._is_music()
        self._loading=True; self._quality(() if music else heights,None if music else self._presets[self.service].max_height); self._loading=False
        self._hint('probe_cancelled' if error=='probe_cancelled' else 'probe_unavailable' if error else
                   'best_selected' if heights else 'quality_per_item')

    def _quality(self,heights,cap):
        self._heights=tuple(heights)
        self.quality_box.clear(); self.quality_box.addItem(self.tr.text('best_available'),None)
        for height in sorted(set(heights)|({cap} if cap is not None else set()),reverse=True):
            self.quality_box.addItem(f'{height}p' if height in heights else self.tr.text('quality_limit',height=height),height)
        self.quality_box.setCurrentIndex(max(0,self.quality_box.findData(cap)))

    def _submit(self): self.submit_requested.emit(self.url_input.text(),self.mode,self.limit_box.currentData())

    def accept_input(self,text):
        try: service=parse_url(text).service
        except ValueError: return
        if self._drafts[service]==text:
            self._drafts[service]=''
            if service==self.service and self.url_input.text()==text: self.url_input.clear()

    def _choose_folder(self):
        folder=QFileDialog.getExistingDirectory(self,self.tr.text('download_folder'),self.folder_input.text())
        if folder: self.folder_input.setText(folder); self._options_changed()

    def _recent(self,index):
        folder=self.recent_box.itemData(index)
        if folder: self.folder_input.setText(folder); self._options_changed()
