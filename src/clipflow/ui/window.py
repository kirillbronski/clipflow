"""First functional Qt workbench; full composer/themes/accounts follow in T11–T13."""
from PySide6.QtCore import Qt,QSize
from PySide6.QtWidgets import (
    QMainWindow,QWidget,QHBoxLayout,QVBoxLayout,QLabel,QPushButton,QLineEdit,QComboBox,
    QListView,QFrame,QFileDialog,QCheckBox,QDialog,QDialogButtonBox,QListWidget,QListWidgetItem,QInputDialog,
)

from clipflow.domain.models import Service,JobState
from clipflow.domain.urls import parse_url
from clipflow.ui.queue_model import QueueFilter,JobListModel
from clipflow.ui.queue_delegate import QueueDelegate,SOURCE_NAMES

STYLE='''
QMainWindow,QWidget { background: #1c1e25; color: #eeedf5; font-family: "Segoe UI", "Helvetica Neue"; font-size: 13px; }
QFrame#sidebar { background: #171920; border-right: 1px solid #30323d; }
QFrame#composer { background: #24262f; border: 1px solid #333541; border-radius: 10px; }
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
QLineEdit,QComboBox { background: #1c1e25; border: 1px solid #3b3d49; border-radius: 6px; padding: 9px; selection-background-color: #6752b2; }
QComboBox QAbstractItemView { background: #24262f; color: #eeedf5; selection-background-color: #4f446d; }
QListView { border: none; background: #1c1e25; outline: none; }
QScrollBar:vertical { background: #1c1e25; width: 9px; }
QScrollBar::handle:vertical { background: #454452; min-height: 30px; border-radius: 4px; }
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height: 0; }
QDialog { background: #24262f; }
QToolTip { background: #302b43; color: #fff; border: 1px solid #83759e; }
'''


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
        self.heading=QLabel('Все загрузки'); self.heading.setObjectName('heading'); main.addWidget(self.heading)
        subtitle=QLabel('Все сервисы. Одна понятная очередь.'); subtitle.setObjectName('muted'); main.addWidget(subtitle)
        self.composer=QFrame(); self.composer.setObjectName('composer'); compose=QVBoxLayout(self.composer); compose.setContentsMargins(18,18,18,18); compose.setSpacing(14)
        mode_line=QHBoxLayout(); mode_line.addWidget(QLabel('Скачать'))
        self.mode_box=QComboBox()
        for label,value in [('Один ролик / пост','single'),('Плейлист YouTube','playlist'),('Урок GetCourse','lesson'),('Профиль Instagram','profile')]:
            self.mode_box.addItem(label,value)
        mode_line.addWidget(self.mode_box); mode_line.addStretch(); compose.addLayout(mode_line)
        entry=QHBoxLayout(); entry.setSpacing(10)
        self.url_input=QLineEdit(); self.url_input.setPlaceholderText('Вставьте ссылку на видео или публикацию'); self.url_input.setMinimumWidth(150)
        self.url_input.setAccessibleName('Ссылка для скачивания')
        self.add_button=QPushButton('↓  Добавить в очередь'); self.add_button.setObjectName('primary'); self.add_button.setMinimumWidth(170)
        entry.addWidget(self.url_input,1); entry.addWidget(self.add_button); compose.addLayout(entry)
        folder_row=QHBoxLayout(); folder_row.addWidget(QLabel('Папка'))
        self.folder_input=QLineEdit(); self.folder_input.setAccessibleName('Папка загрузок')
        choose=QPushButton('Выбрать…'); choose.clicked.connect(self._choose_folder)
        folder_row.addWidget(self.folder_input,1); folder_row.addWidget(choose); compose.addLayout(folder_row)
        options=QHBoxLayout(); self.summary=QLabel(); self.summary.setObjectName('muted'); options.addWidget(self.summary,1)
        self.auto_start=QCheckBox('Автозапуск'); self.auto_start.setChecked(presenter.settings.auto_start)
        self.auto_start.toggled.connect(self._set_auto_start); options.addWidget(self.auto_start); compose.addLayout(options)
        main.addWidget(self.composer)
        self.error_label=QLabel(); self.error_label.setObjectName('error'); self.error_label.setWordWrap(True); self.error_label.hide(); main.addWidget(self.error_label)
        queue_header=QHBoxLayout(); self.count_label=QLabel('Очередь'); queue_header.addWidget(self.count_label,1)
        self.start_button=QPushButton('▷  Запустить очередь'); self.start_button.clicked.connect(presenter.start_queue); queue_header.addWidget(self.start_button)
        main.addLayout(queue_header)
        self.queue_view=QListView(); self.queue_view.setUniformItemSizes(True); self.queue_view.setSpacing(0)
        self.proxy=QueueFilter(presenter.model,self); self.queue_view.setModel(self.proxy)
        delegate=QueueDelegate(self.queue_view); self.queue_view.setItemDelegate(delegate)
        delegate.action_requested.connect(self._row_action)
        self.queue_view.activated.connect(lambda index:presenter.toggle_job(index.data(JobListModel.JobIdRole)))
        main.addWidget(self.queue_view,1)
        self.empty=QLabel('Здесь пока нет заданий. Добавьте первую ссылку.'); self.empty.setObjectName('muted'); main.addWidget(self.empty)
        footer=QLabel('Файлы сохраняются локально  ·  ClipFlow 2.0 · preview'); footer.setObjectName('muted'); main.addWidget(footer)
        self.add_button.clicked.connect(self._submit); self.url_input.returnPressed.connect(self._submit)
        self.url_input.textChanged.connect(self._detect_service)
        presenter.input_accepted.connect(self._input_accepted); presenter.jobs_changed.connect(self._update_counts)
        presenter.error_raised.connect(self._show_error); presenter.settings_changed.connect(self._settings_changed)
        presenter.selection_requested.connect(self._select_dialog); presenter.source_requested.connect(self._source_dialog)
        presenter.shutdown_finished.connect(self._shutdown_finished)
        self._settings_changed(); self._update_counts()

    def _settings_changed(self):
        options=self.presenter.settings.presets[self._service]
        self.folder_input.setText(str(options.folder))
        quality=f'{options.max_height}p' if options.max_height else 'Лучшее качество'
        self.summary.setText(f'{SOURCE_NAMES[self._service.value]}  ·  {options.format.upper()}  ·  {quality}')

    def _detect_service(self,text):
        try: service=parse_url(text).service
        except ValueError: return
        if service!=self._service: self._service=service; self._settings_changed()

    def _submit(self):
        text=self.url_input.text()
        try: service=parse_url(text).service
        except ValueError: self._show_error('invalid_link'); return
        if self.folder_input.text()!=str(self.presenter.settings.presets[service].folder):
            if not self.presenter.update_folder(service,self.folder_input.text()): return
        self.presenter.submit(text,self.mode_box.currentData())

    def _input_accepted(self,text):
        if self.url_input.text()==text: self.url_input.clear()
        self.error_label.hide()

    def _choose_folder(self):
        path=QFileDialog.getExistingDirectory(self,'Папка загрузок',self.folder_input.text())
        if path: self.presenter.update_folder(self._service,path)

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
        self.proxy.show_source(service,history); self.heading.setText(title); self.composer.setVisible(not history)
        if service is not None:
            self._service=Service(service); self._settings_changed()
        self._update_counts()

    def _show_error(self,code):
        messages={'invalid_link':'Проверьте ссылку и выбранный режим.', 'already_queued':'Эта загрузка уже есть в списке.',
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
        buttons.accepted.connect(accept); self._dialogs.append(dialog); dialog.open()

    def _source_dialog(self,identity):
        dialog=QInputDialog(self); dialog.setWindowTitle('Восстановить источник')
        dialog.setLabelText('Вставьте исходную ссылку этого задания:'); dialog.setInputMode(QInputDialog.InputMode.TextInput)
        dialog.textValueSelected.connect(lambda text:self.presenter.provide_source(identity,text))
        self._dialogs.append(dialog); dialog.open()

    def _shutdown_finished(self):
        if self._closing_requested: self.close()

    def closeEvent(self,event):
        self._closing_requested=True
        for dialog in self._dialogs: dialog.reject()
        self.presenter.shutdown()
        if self.presenter.is_closed: event.accept()
        else:
            self.setEnabled(False); event.ignore()
