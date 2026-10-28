"""First functional Qt workbench; full composer/themes/accounts follow in T11–T13."""
from PySide6.QtCore import Qt,QSize
from PySide6.QtWidgets import (
    QMainWindow,QWidget,QHBoxLayout,QVBoxLayout,QLabel,QPushButton,QLineEdit,QComboBox,
    QListView,QFrame,QFileDialog,QCheckBox,QDialog,QDialogButtonBox,QListWidget,QListWidgetItem,QInputDialog,QScrollArea,
)

from clipflow.domain.models import Service,JobState
from clipflow.domain.urls import parse_url,request_key
from clipflow.ui.queue_model import QueueFilter,JobListModel
from clipflow.ui.queue_delegate import QueueDelegate,SOURCE_NAMES
from clipflow.ui.composer import Composer
from clipflow.ui.batch_dialog import BatchDialog

STYLE='''
QMainWindow,QWidget { background: #1c1e25; color: #eeedf5; font-family: "Segoe UI", "Helvetica Neue"; font-size: 13px; }
QFrame#sidebar { background: #171920; border-right: 1px solid #30323d; }
QFrame#composer { background: #24262f; border: 1px solid #333541; border-radius: 10px; }
QWidget#composerSection { background: transparent; }
QLabel { background: transparent; }
QLabel#muted { color: #aaa9ba; font-size: 12px; }
QLabel#heading { font-size: 25px; font-weight: 700; }
QLabel#brand { font-size: 20px; font-weight: 700; padding: 8px; }
QLabel#error { color: #edaaaa; }
QPushButton { background: #242630; border: 1px solid #3b3d4c; border-radius: 7px; padding: 9px 13px; }
QPushButton:hover { background: #30323e; border-color: #767087; }
QPushButton:pressed { background: #3c3752; }
QPushButton:focus,QLineEdit:focus,QComboBox:focus { border: 1px solid #aa98fc; }
QPushButton:disabled { color: #686779; border-color: #323440; }
QPushButton#primary { background: #8d77ed; color: #ffffff; border-color: #a08af7; font-weight: 600; }
QPushButton#nav { text-align: left; background: transparent; border: none; padding: 11px; }
QPushButton#nav:checked { background: #332e4a; color: #b8a8ff; }
QPushButton#mode:checked { background: #3a3255; border-color: #9b88f5; color: #ffffff; font-weight: 600; }
QToolButton { background: transparent; border: none; color: #aaa9ba; padding: 4px; }
QLineEdit,QComboBox { background: #1c1e25; border: 1px solid #3b3d49; border-radius: 6px; padding: 9px; selection-background-color: #6752b2; }
QComboBox QAbstractItemView { background: #24262f; color: #eeedf5; selection-background-color: #4f446d; }
QListView { border: none; background: #1c1e25; outline: none; }
QScrollBar:vertical { background: #1c1e25; width: 9px; }
QScrollBar::handle:vertical { background: #454452; min-height: 30px; border-radius: 4px; }
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height: 0; }
QDialog { background: #24262f; }
QToolTip { background: #302b43; color: #fff; border: 1px solid #83759e; }
'''


class QueueView(QListView):
    """Return/Enter activate once on both platforms; keep native navigation."""
    def keyPressEvent(self,event):
        if event.key() in {Qt.Key.Key_Return,Qt.Key.Key_Enter} and event.modifiers() in {Qt.KeyboardModifier.NoModifier,Qt.KeyboardModifier.KeypadModifier}:
            if not event.isAutoRepeat() and self.currentIndex().isValid():
                self.activated.emit(self.currentIndex())
            event.accept()
        else: super().keyPressEvent(event)


class MainWindow(QMainWindow):
    def __init__(self,presenter):
        super().__init__()
        self.presenter=presenter; presenter.setParent(self)
        self._closing_requested=False; self._dialogs=[]; self._service=Service.YOUTUBE
        self.setWindowTitle('ClipFlow · Qt preview'); self.setMinimumSize(880,680); self.resize(1180,800)
        self.setStyleSheet(STYLE)
        root=QWidget(); self.setCentralWidget(root); layout=QHBoxLayout(root); layout.setContentsMargins(0,0,0,0); layout.setSpacing(0)
        sidebar=QFrame(); sidebar.setObjectName('sidebar'); sidebar.setFixedWidth(180)
        side=QVBoxLayout(sidebar); side.setContentsMargins(14,22,14,20); side.setSpacing(8)
        brand=QLabel('↓  ClipFlow'); brand.setObjectName('brand'); side.addWidget(brand); side.addSpacing(20)
        self.nav_buttons=[]
        for label,service,history in [('Все загрузки',None,False),('История',None,True),('YouTube','youtube',False),
                                      ('Instagram','instagram',False),('GetCourse','getcourse',False)]:
            button=QPushButton(label); button.setObjectName('nav'); button.setCheckable(True)
            button.clicked.connect(lambda checked=False,s=service,h=history,t=label:self._navigate(s,h,t))
            side.addWidget(button); self.nav_buttons.append(button)
        self.nav_buttons[0].setChecked(True)
        side.addStretch(); local=QLabel('Файлы остаются\nна этом компьютере'); local.setObjectName('muted'); side.addWidget(local)
        layout.addWidget(sidebar)
        main=QVBoxLayout(); main.setContentsMargins(28,28,28,18); main.setSpacing(16); layout.addLayout(main,1)
        header=QHBoxLayout(); self.heading=QLabel('Все загрузки'); self.heading.setObjectName('heading'); header.addWidget(self.heading,1)
        self.batch_button=QPushButton('+  Несколько ссылок'); self.batch_button.clicked.connect(self._open_batch); header.addWidget(self.batch_button); main.addLayout(header)
        subtitle=QLabel('Все сервисы. Одна понятная очередь.'); subtitle.setObjectName('muted'); main.addWidget(subtitle)
        self.composer=Composer(presenter.settings,self)
        self.url_input=self.composer.url_input; self.add_button=self.composer.add_button
        self.folder_input=self.composer.folder_input; self.summary=self.composer.summary; self.auto_start=self.composer.auto_start
        self.auto_start.toggled.connect(self._set_auto_start)
        self.composer_host=QScrollArea(); self.composer_host.setWidgetResizable(True); self.composer_host.setFrameShape(QFrame.Shape.NoFrame)
        self.composer_host.setMinimumHeight(210); self.composer_host.setMaximumHeight(380); self.composer_host.setWidget(self.composer)
        main.addWidget(self.composer_host)
        self.error_label=QLabel(); self.error_label.setObjectName('error'); self.error_label.setWordWrap(True); self.error_label.hide(); main.addWidget(self.error_label)
        queue_header=QHBoxLayout(); self.count_label=QLabel('Очередь'); queue_header.addWidget(self.count_label,1)
        self.start_button=QPushButton('▷  Запустить очередь'); self.start_button.clicked.connect(presenter.start_queue); queue_header.addWidget(self.start_button)
        main.addLayout(queue_header)
        self.queue_view=QueueView(); self.queue_view.setUniformItemSizes(True); self.queue_view.setSpacing(0)
        self.proxy=QueueFilter(presenter.model,self); self.queue_view.setModel(self.proxy)
        delegate=QueueDelegate(self.queue_view); self.queue_view.setItemDelegate(delegate)
        delegate.action_requested.connect(self._row_action)
        self.queue_view.activated.connect(lambda index:presenter.toggle_job(index.data(JobListModel.JobIdRole)))
        main.addWidget(self.queue_view,1)
        self.empty=QLabel('Здесь пока нет заданий. Добавьте первую ссылку.'); self.empty.setObjectName('muted'); main.addWidget(self.empty)
        footer=QLabel('Файлы сохраняются локально  ·  ClipFlow 2.0 · preview'); footer.setObjectName('muted'); main.addWidget(footer)
        self.composer.submit_requested.connect(self._submit)
        self.composer.probe_requested.connect(self._request_probe); self.composer.batch_requested.connect(self._open_batch)
        self.composer.preset_changed.connect(self._save_preset); presenter.probe_ready.connect(self.composer.apply_probe)
        presenter.input_accepted.connect(self._input_accepted); presenter.jobs_changed.connect(self._update_counts)
        presenter.error_raised.connect(self._show_error); presenter.settings_changed.connect(self._settings_changed)
        presenter.selection_requested.connect(self._select_dialog); presenter.source_requested.connect(self._source_dialog)
        presenter.shutdown_finished.connect(self._shutdown_finished)
        self._settings_changed(); self._update_counts()

    def _settings_changed(self):
        self.composer.set_settings(self.presenter.settings)
        self.auto_start.blockSignals(True); self.auto_start.setChecked(self.presenter.settings.auto_start); self.auto_start.blockSignals(False)

    def _save_preset(self,service,options,limit):
        return self.presenter.update_preset(service,options,limit)

    def _commit_options(self):
        try: options=self.composer.options()
        except ValueError: self._show_error('invalid_folder'); return False
        return self._save_preset(self.composer.service,options,self.composer.limit_box.currentData())

    def _submit(self,text,mode,limit):
        if self._commit_options(): self.presenter.submit(text,mode,limit)

    def _request_probe(self,text,identity):
        try: options=self.composer.options()
        except ValueError: text=''; options=None
        self.presenter.request_probe(text,identity,options,self.composer.mode,self.composer.limit_box.currentData())

    def _open_batch(self):
        for dialog in self._dialogs:
            if isinstance(dialog,BatchDialog) and dialog.isVisible(): dialog.raise_(); return
        if not self._commit_options(): return
        existing={request_key(job.request) for job in self.presenter.model.jobs}
        dialog=BatchDialog(self.presenter.submission,self.presenter.settings.presets,self.composer.limit_box.currentData(),self,existing_keys=existing)
        def confirm(preview):
            result=self.presenter.submit_preview(preview)
            if result is not None:
                self.error_label.hide()
                if not result.added and result.existing: self._show_error('already_queued')
                dialog.accept()
        dialog.confirmed.connect(confirm); self._track_dialog(dialog); dialog.open()

    def _track_dialog(self,dialog):
        self._dialogs.append(dialog)
        def finished(result):
            if dialog in self._dialogs: self._dialogs.remove(dialog)
            dialog.deleteLater()
        dialog.finished.connect(finished)

    def _input_accepted(self,text):
        self.composer.accept_input(text)
        self.error_label.hide()

    def _set_auto_start(self,enabled):
        if not self.presenter.set_auto_start(enabled):
            self.auto_start.blockSignals(True); self.auto_start.setChecked(self.presenter.settings.auto_start); self.auto_start.blockSignals(False)

    def _update_counts(self):
        count=self.presenter.model.rowCount()
        word='задание' if count%10==1 and count%100!=11 else 'задания' if 2<=count%10<=4 and not 12<=count%100<=14 else 'заданий'
        self.count_label.setText(f'Очередь  ·  {count} {word}')
        self.empty.setVisible(self.proxy.rowCount()==0)

    def _row_action(self,identity,action):
        if action=='cancel': self.presenter.cancel_job(identity)
        else: self.presenter.toggle_job(identity)

    def _navigate(self,service,history,title):
        for button in self.nav_buttons: button.setChecked(button.text()==title)
        self.proxy.show_source(service,history); self.heading.setText(title); self.composer_host.setVisible(not history); self.composer.setVisible(not history)
        if service is not None:
            self.composer.set_service(Service(service))
        self._update_counts()

    def _show_error(self,code):
        messages={'invalid_link':'Проверьте ссылку и выбранный режим.', 'already_queued':'Эта загрузка уже есть в списке.',
                  'invalid_folder':'Укажите папку для скачивания.',
                  'folder_missing':'Папка недоступна. Проверьте путь.', 'storage_busy':'Хранилище занято. Повторите действие позже.',
                  'storage_read_only':'Нет доступа для записи в папку данных ClipFlow.',
                  'queue_update_failed':'Не удалось сохранить очередь. Загрузки остановлены.',
                  'source_changed':'Ссылка отличается от исходной. Добавьте её как новое задание.',
                  'cooldown_active':'Срок ожидания ещё не истёк. Повторите позже.',
                  'settings_reset':'Повреждённые настройки сохранены в резервной копии. Восстановлены начальные параметры.',
                  'legacy_settings_reset':'Старые настройки не удалось прочитать. Восстановлены начальные параметры.',
                  'app_closed':'Очередь закрыта. Перезапустите приложение.'}
        self.error_label.setText(messages.get(code,'Не удалось выполнить действие. Проверьте доступ и повторите попытку.'))
        self.error_label.setToolTip(code); self.error_label.show()

    def _select_dialog(self,identity,selection):
        if selection is None:
            self._show_error('selection_refresh_required')
            return
        dialog=QDialog(self); dialog.setWindowTitle('Выберите видео урока'); dialog.resize(520,350)
        layout=QVBoxLayout(dialog); layout.addWidget(QLabel('Какие материалы добавить в очередь?'))
        items=QListWidget(); layout.addWidget(items)
        for number,code in enumerate(selection.ids):
            title=selection.titles[number] if number<len(selection.titles) else f'Видео {number+1}'
            item=QListWidgetItem(title); item.setData(Qt.ItemDataRole.UserRole,code); item.setCheckState(Qt.CheckState.Checked); items.addItem(item)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel); layout.addWidget(buttons)
        buttons.rejected.connect(dialog.reject)
        def accept():
            ids=tuple(items.item(n).data(Qt.ItemDataRole.UserRole) for n in range(items.count()) if items.item(n).checkState()==Qt.CheckState.Checked)
            if ids: self.presenter.select_items(identity,ids); dialog.accept()
        buttons.accepted.connect(accept); self._track_dialog(dialog); dialog.open()

    def _source_dialog(self,identity):
        dialog=QInputDialog(self); dialog.setWindowTitle('Восстановить источник')
        dialog.setLabelText('Вставьте исходную ссылку этого задания:'); dialog.setInputMode(QInputDialog.InputMode.TextInput)
        dialog.textValueSelected.connect(lambda text:self.presenter.provide_source(identity,text))
        self._track_dialog(dialog); dialog.open()

    def _shutdown_finished(self):
        if self._closing_requested: self.close()

    def closeEvent(self,event):
        self._closing_requested=True
        for dialog in tuple(self._dialogs): dialog.reject()
        self.presenter.shutdown()
        if self.presenter.is_closed: event.accept()
        else:
            self.setEnabled(False); event.ignore()
