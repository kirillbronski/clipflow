"""Qt workbench following the approved desktop composition and shared commands."""

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from clipflow.domain.models import JobState, Service
from clipflow.domain.urls import request_key
from clipflow.ui.accounts import AccountsPage
from clipflow.ui.batch_dialog import BatchDialog
from clipflow.ui.composer import Composer
from clipflow.ui.i18n import CATALOG, Translator
from clipflow.ui.input import InputActions
from clipflow.ui.job_status import SOURCE_NAMES
from clipflow.ui.queue_model import JobListModel
from clipflow.ui.queue_panel import QueuePanel
from clipflow.ui.settings_page import SettingsPage
from clipflow.ui.sidebar import Sidebar
from clipflow.ui.themes import ThemeManager, application_icon, glyph_icon
from clipflow.version import APP_VERSION


class MainWindow(QMainWindow):
    def __init__(self, presenter):
        super().__init__()
        self.presenter = presenter
        presenter.setParent(self)
        self._closing_requested = False
        self._ui_disposed = False
        self._dialogs = []
        self._service = Service.YOUTUBE
        self.setWindowTitle(f'ClipFlow {APP_VERSION}')
        self.setMinimumSize(880, 680)
        self.resize(1180, 800)
        self.setWindowIcon(application_icon())
        self.tr = Translator(presenter.settings.language, self)
        self.tr.install_qt()
        self.theme = ThemeManager(QApplication.instance(), presenter.settings, self)
        self._nav_key = 'all_downloads'
        self._error_code = None
        self._section = 'downloads'
        self._input_actions = InputActions(self, self.tr)
        QApplication.instance().installEventFilter(self._input_actions)
        QApplication.instance().aboutToQuit.connect(self.dispose_ui)
        root = QWidget()
        root.setObjectName('root')
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.sidebar = Sidebar(self.tr)
        self.nav_buttons = self.sidebar.nav_buttons
        self.accounts_button = self.sidebar.accounts_button
        self.settings_button = self.sidebar.settings_button
        self.sidebar.navigate.connect(self._navigate)
        self.sidebar.section.connect(self._show_section)
        layout.addWidget(self.sidebar)
        self.main_page = QScrollArea()
        self.main_page.setWidgetResizable(True)
        self.main_page.setFrameShape(QFrame.Shape.NoFrame)
        self.main_page.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName('mainContent')
        self.main_page.setWidget(content)
        layout.addWidget(self.main_page, 1)
        main = QVBoxLayout(content)
        main.setContentsMargins(36, 32, 36, 18)
        main.setSpacing(20)
        self.main_layout = main
        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(5)
        self.heading = self.tr.widget(QLabel, 'all_downloads')
        self.heading.setObjectName('heading')
        titles.addWidget(self.heading)
        header.addLayout(titles, 1)
        self.batch_button = self.tr.widget(QPushButton, 'batch')
        self.batch_button.clicked.connect(self._open_batch)
        header.addWidget(self.batch_button)
        main.addLayout(header)
        subtitle = QLabel()
        self.subtitle = subtitle
        subtitle.setObjectName('muted')
        subtitle.setWordWrap(True)
        titles.addWidget(subtitle)
        self.composer = Composer(presenter.settings, self, translator=self.tr)
        self.url_input = self.composer.url_input
        self.add_button = self.composer.add_button
        self.folder_input = self.composer.folder_input
        self.summary = self.composer.summary
        self.auto_start = self.composer.auto_start
        self.auto_start.toggled.connect(self._set_auto_start)
        self.composer_host = QScrollArea()
        self.composer_host.setWidgetResizable(True)
        self.composer_host.setFrameShape(QFrame.Shape.NoFrame)
        self.composer_host.setWidget(self.composer)
        self.composer.parameters_button.toggled.connect(self._resize_composer)
        self.composer.layout_changed.connect(self._resize_composer)
        for button in self.composer.mode_buttons.values():
            button.clicked.connect(self._resize_composer)
        main.addWidget(self.composer_host)
        self.error_label = QLabel()
        self.error_label.setObjectName('error')
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        main.addWidget(self.error_label)
        self.queue_panel = panel = QueuePanel(presenter, self.theme, self.tr)
        self.queue_toolbar = panel.toolbar
        self.count_label = panel.count_label
        self.start_button = panel.start_button
        self.cancel_queue_button = panel.cancel_queue_button
        self.clear_all_button = panel.clear_all_button
        self.status_tabs = panel.status_tabs
        self.status_buttons = panel.status_buttons
        self.queue_view = panel.queue_view
        self.proxy = panel.proxy
        self.empty = panel.empty
        panel.clear_all_requested.connect(self._confirm_clear_all)
        panel.row_action.connect(self._row_action)
        panel.context_menu.connect(self._history_menu)
        panel.status_changed.connect(self._update_counts)
        main.addWidget(panel, 1)
        self._download_widgets = (
            self.queue_panel,
            self.batch_button,
            self.composer_host,
            self.queue_toolbar,
            self.count_label,
            self.start_button,
            self.cancel_queue_button,
            self.clear_all_button,
            self.status_tabs,
            self.queue_view,
            self.empty,
            subtitle,
        )
        self.accounts_page = AccountsPage(presenter, self.tr, self)
        self.settings_page = SettingsPage(presenter, self.tr, self)
        main.addWidget(self.accounts_page, 1)
        main.addWidget(self.settings_page, 1)
        self.accounts_page.hide()
        self.settings_page.hide()
        self.composer.submit_requested.connect(self._submit)
        self.composer.probe_requested.connect(self._request_probe)
        self.composer.batch_requested.connect(self._open_batch)
        self.composer.preset_changed.connect(self._save_preset)
        presenter.probe_ready.connect(self.composer.apply_probe)
        presenter.auth_changed.connect(self.composer._invalidate)
        presenter.input_accepted.connect(self._input_accepted)
        presenter.jobs_changed.connect(self._update_counts)
        presenter.error_raised.connect(self._show_error)
        presenter.settings_changed.connect(self._settings_changed)
        presenter.selection_requested.connect(self._select_dialog)
        presenter.source_requested.connect(self._source_dialog)
        presenter.shutdown_finished.connect(self._shutdown_finished)
        self._menus()
        self.tr.changed.connect(self.retranslate)
        self.theme.changed.connect(self._accent)
        self.composer.service_changed.connect(self._accent)
        self.presenter.model.translator = self.tr
        self._settings_changed()
        self._update_counts()
        self._accent()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'composer_host'):
            self.sidebar.set_compact(self.width() < 1000)
            margin = 24 if self.width() < 1000 else 36
            self.main_layout.setContentsMargins(margin, 32, margin, 18)
            self._resize_composer()
            self._arrange_queue_controls()

    def _arrange_queue_controls(self):
        def apply():
            if self._section != 'downloads':
                return
            margins = self.main_layout.contentsMargins()
            available = self.main_page.viewport().width() - margins.left() - margins.right()
            self.queue_panel.arrange(available)

        QTimer.singleShot(0, self, apply)

    def _resize_composer(self, *args):
        def apply():
            instagram = self.composer.service == Service.INSTAGRAM
            height = max(170, self.composer.sizeHint().height() + 2)
            self.composer_host.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff
                if instagram
                else Qt.ScrollBarPolicy.ScrollBarAsNeeded
            )
            self.composer_host.setFixedHeight(
                height if instagram else min(height, 380, int(self.height() * 0.44))
            )

        QTimer.singleShot(0, self, apply)

    def _menus(self):
        bar = self.menuBar()
        bar.setNativeMenuBar(True)
        downloads = self.downloads_menu = bar.addMenu('')
        self.tr.bind(downloads, 'menu_downloads', setter='setTitle')
        action = downloads.addAction('')
        self.tr.bind(action, 'batch')
        action.setShortcuts(QKeySequence.keyBindings(QKeySequence.StandardKey.New))
        action.triggered.connect(self._open_batch)
        self.addAction(action)
        action = downloads.addAction('')
        self.tr.bind(action, 'start_queue')
        action.triggered.connect(self.presenter.start_queue)
        downloads.addSeparator()
        for key, command in [
            ('cancel_queue', self.presenter.cancel_queue),
            ('clear_all', self._confirm_clear_all),
            ('clear_queue', self.presenter.clear_queue),
            ('clear_history', self.presenter.clear_history),
        ]:
            action = downloads.addAction('')
            self.tr.bind(action, key)
            if key in {'clear_queue', 'clear_history'}:
                self.tr.bind(action, 'keeps_files_hint', setter='setToolTip')
            action.triggered.connect(command)
        downloads.setToolTipsVisible(True)
        edit = bar.addMenu('')
        self.tr.bind(edit, 'menu_edit', setter='setTitle')
        for key, method, standard in [
            ('undo', 'undo', 'Undo'),
            ('redo', 'redo', 'Redo'),
            ('cut', 'cut', 'Cut'),
            ('copy', 'copy', 'Copy'),
            ('paste', 'paste', 'Paste'),
            ('select_all', 'selectAll', 'SelectAll'),
        ]:
            action = edit.addAction('')
            self.tr.bind(action, key)
            action.setShortcuts(
                QKeySequence.keyBindings(getattr(QKeySequence.StandardKey, standard))
            )
            self.addAction(action)
            action.triggered.connect(lambda checked=False, m=method: self._edit(m))
        edit.aboutToShow.connect(lambda: self._edit_enabled(edit))
        view = bar.addMenu('')
        self.tr.bind(view, 'menu_view', setter='setTitle')
        themes = view.addMenu('')
        self.tr.bind(themes, 'theme', setter='setTitle')
        self.theme_actions = {}
        group = QActionGroup(self)
        for mode in ('dark', 'light', 'system'):
            action = themes.addAction('')
            self.tr.bind(action, mode)
            action.setCheckable(True)
            group.addAction(action)
            self.theme_actions[mode] = action
            action.triggered.connect(lambda checked=False, m=mode: self._preferences(theme=m))
        settings = bar.addMenu('')
        self.tr.bind(settings, 'menu_settings', setter='setTitle')
        languages = settings.addMenu('')
        self.tr.bind(languages, 'language', setter='setTitle')
        self.language_actions = {}
        group = QActionGroup(self)
        for code, label in [('ru', 'Русский'), ('en', 'English')]:
            action = languages.addAction(label)
            action.setCheckable(True)
            group.addAction(action)
            self.language_actions[code] = action
            action.triggered.connect(lambda checked=False, c=code: self._preferences(language=c))
        # Explicit wrappers keep the native menu/language-binding lifetime clear.
        self._menu_objects = [downloads, edit, view, themes, settings, languages]

    def _edit(self, method):
        widget = QApplication.focusWidget()
        if widget is not None and self._input_actions.owns(widget) and hasattr(widget, method):
            getattr(widget, method)()

    def _edit_enabled(self, menu):
        widget = QApplication.focusWidget()
        for action in menu.actions():
            action.setEnabled(widget is not None and hasattr(widget, 'paste'))

    def _preferences(self, **values):
        self.presenter.update_preferences(**values)
        self._settings_changed()  # Also roll back checkmarks if persistence failed.

    def _accent(self, *args):
        t = self.theme.tokens()
        color = t[self.composer.service.value]
        background = color
        if self.composer.service == Service.INSTAGRAM:
            start = '#a93d85' if self.theme.resolved_mode() == 'light' else '#f3aed9'
            background = f'qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {start},stop:1 {color})'
        self.setStyleSheet(
            f'QPushButton#primary {{background:{background};color:{t["accent_text"]};'
            f'border-color:{color};}} '
            f'QPushButton#statusTab:checked {{border-bottom-color:{color};}}'
        )
        self.queue_view.viewport().update()
        for button, glyph, color in (
            (self.composer.add_button, '↓', t['accent_text']),
            (self.start_button, '▷', t['text']),
            (self.batch_button, '+', t['text']),
        ):
            # Never taller than the text line, so the button keeps its neighbours' height.
            button.ensurePolished()
            size = min(16, button.fontMetrics().height())
            button.setIconSize(QSize(size, size))
            button.setIcon(glyph_icon(glyph, color, size))
        self.sidebar.paint_sources(t)
        self._subtitle()
        self._resize_composer()

    def _subtitle(self):
        key = (
            self.composer.service.value + '_subtitle'
            if self._nav_key in SOURCE_NAMES.values()
            else 'subtitle'
        )
        self.subtitle.setText(self.tr.text(key))

    def retranslate(self):
        self.heading.setText(
            self.tr.text(self._nav_key)
            if self._nav_key in CATALOG[self.tr.language]
            else self._nav_key
        )
        self._update_counts()
        self.queue_view.viewport().update()
        self._subtitle()
        self._resize_composer()
        if self.presenter.model.rowCount():
            self.presenter.model.dataChanged.emit(
                self.presenter.model.index(0),
                self.presenter.model.index(self.presenter.model.rowCount() - 1),
            )
        if self._error_code and self.error_label.isVisible():
            self._show_error(self._error_code)

    def _settings_changed(self):
        self.composer.set_settings(self.presenter.settings)
        self.theme.set_mode(self.presenter.settings.theme)
        self.tr.set_language(self.presenter.settings.language)
        if hasattr(self, 'theme_actions'):
            self.theme_actions[self.presenter.settings.theme].setChecked(True)
            self.language_actions[self.presenter.settings.language].setChecked(True)
        self.auto_start.blockSignals(True)
        self.auto_start.setChecked(self.presenter.settings.auto_start)
        self.auto_start.blockSignals(False)

    def _save_preset(self, service, options, limit):
        return self.presenter.update_preset(service, options, limit)

    def _commit_options(self):
        try:
            options = self.composer.preset_options()
        except ValueError:
            self._show_error('invalid_folder')
            return False
        return self._save_preset(
            self.composer.service, options, self.composer.limit_box.currentData()
        )

    def _submit(self, text, mode, limit):
        if self._commit_options():
            self.presenter.submit(text, mode, limit)

    def _request_probe(self, text, identity):
        try:
            options = self.composer.options()
        except ValueError:
            text = ''
            options = None
        self.presenter.request_probe(
            text, identity, options, self.composer.mode, self.composer.limit_box.currentData()
        )

    def _open_batch(self):
        for dialog in self._dialogs:
            if isinstance(dialog, BatchDialog) and dialog.isVisible():
                dialog.raise_()
                return
        if not self._commit_options():
            return
        existing = {request_key(job.request) for job in self.presenter.model.jobs}
        dialog = BatchDialog(
            self.presenter.submission,
            self.presenter.settings.presets,
            self.composer.limit_box.currentData(),
            self,
            existing_keys=existing,
            translator=self.tr,
        )

        def confirm(preview):
            result = self.presenter.submit_preview(preview)
            if result is not None:
                self.error_label.hide()
                if not result.added and result.existing:
                    self._show_error('already_queued')
                dialog.accept()

        dialog.confirmed.connect(confirm)
        self._track_dialog(dialog)
        dialog.open()

    def _track_dialog(self, dialog):
        self._dialogs.append(dialog)

        def finished(result):
            if dialog in self._dialogs:
                self._dialogs.remove(dialog)
            dialog.deleteLater()

        dialog.finished.connect(finished)

    def _input_accepted(self, text):
        self.composer.accept_input(text)
        self.error_label.hide()

    def _set_auto_start(self, enabled):
        if not self.presenter.set_auto_start(enabled):
            self.auto_start.blockSignals(True)
            self.auto_start.setChecked(self.presenter.settings.auto_start)
            self.auto_start.blockSignals(False)

    def _update_counts(self, *args):
        self.queue_panel.update_counts(self._section == 'downloads')
        self._arrange_queue_controls()
        self.sidebar.set_counts(self.presenter.model.jobs)

    def _row_action(self, identity, action):
        if action == 'cancel':
            self.presenter.cancel_job(identity)
        else:
            self.presenter.toggle_job(identity)

    def _history_menu(self, position):
        index = self.queue_view.indexAt(position)
        if not index.isValid():
            return
        if not self.queue_view.selectionModel().isSelected(index):
            self.queue_view.setCurrentIndex(index)
        identities = tuple(
            i.data(JobListModel.JobIdRole) for i in self.queue_view.selectionModel().selectedRows()
        )
        jobs = tuple(self.presenter.repository.get(identity) for identity in identities)
        menu = QMenu(self)
        action = menu.addAction(self.tr.text('open_folder'))
        action.triggered.connect(lambda: self.presenter.open_result(identities[0]))
        terminal = all(
            j.state in {JobState.COMPLETED, JobState.CANCELLED, JobState.FAILED} for j in jobs
        )
        action = menu.addAction(self.tr.text('repeat_job'))
        action.setEnabled(terminal)
        action.triggered.connect(
            lambda: [self.presenter.repeat_job(identity) for identity in identities]
        )
        menu.addSeparator()
        action = menu.addAction(self.tr.text('remove_list'))
        action.setEnabled(terminal and self.presenter.executor.is_idle)
        action.triggered.connect(lambda: self.presenter.remove_jobs(identities))
        action = menu.addAction(self.tr.text('delete_files'))
        action.setEnabled(
            terminal and self.presenter.executor.is_idle and any(j.result_files for j in jobs)
        )
        action.triggered.connect(lambda: self._confirm_delete(identities))
        menu.aboutToHide.connect(menu.deleteLater)
        menu.popup(self.queue_view.viewport().mapToGlobal(position))

    def _confirm_clear_all(self):
        count = len(self.presenter.repository.list())
        if not count:
            return
        dialog = QMessageBox(self)
        self.tr.bind(dialog, 'clear_all_confirm', setter='setWindowTitle')
        self.tr.bind(dialog, 'clear_all_confirmation', count=count)
        dialog.setIcon(QMessageBox.Icon.Warning)
        checkbox = self.tr.widget(QCheckBox, 'clear_all_delete_files')
        checkbox.setChecked(False)
        dialog.setCheckBox(checkbox)
        dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        dialog.setDefaultButton(QMessageBox.StandardButton.No)
        self.tr.bind(dialog.button(QMessageBox.StandardButton.Yes), 'clear_all_confirm')
        self.tr.bind(dialog.button(QMessageBox.StandardButton.No), 'cancel')
        dialog.finished.connect(
            lambda result: (
                self.presenter.clear_all(delete_files=checkbox.isChecked())
                if result == QMessageBox.StandardButton.Yes
                else None
            )
        )
        self._track_dialog(dialog)
        dialog.open()

    def _confirm_delete(self, identities):
        jobs = tuple(self.presenter.repository.get(identity) for identity in identities)
        count = len({path for job in jobs for path in job.result_files})
        if not count:
            return
        dialog = QMessageBox(self)
        self.tr.bind(dialog, 'delete_files', setter='setWindowTitle')
        self.tr.bind(dialog, 'delete_confirmation', count=count)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        dialog.setDefaultButton(QMessageBox.StandardButton.No)
        self.tr.bind(dialog.button(QMessageBox.StandardButton.Yes), 'delete_files')
        self.tr.bind(dialog.button(QMessageBox.StandardButton.No), 'cancel')
        dialog.finished.connect(
            lambda result: (
                self.presenter.delete_files(identities, True)
                if result == QMessageBox.StandardButton.Yes
                else None
            )
        )
        self._track_dialog(dialog)
        dialog.open()

    def _navigate(self, service, history, title):
        self.sidebar.select(nav_key=title)
        self._section = 'downloads'
        self.accounts_page.hide()
        self.settings_page.hide()
        for widget in self._download_widgets:
            widget.show()
        self.proxy.show_source(service, history)
        self._nav_key = title
        self.heading.setText(self.tr.text(title) if title in CATALOG[self.tr.language] else title)
        self.composer_host.setVisible(not history)
        self.composer.setVisible(not history)
        if service is not None:
            self.composer.set_service(Service(service))
        self._update_counts()
        self._subtitle()
        self._resize_composer()

    def _show_section(self, section):
        self._section = section
        self.sidebar.select(section=section)
        for widget in self._download_widgets:
            widget.hide()
        self.accounts_page.setVisible(section == 'accounts')
        self.settings_page.setVisible(section == 'settings')
        self._nav_key = 'accounts' if section == 'accounts' else 'menu_settings'
        self.heading.setText(self.tr.text(self._nav_key))
        self.accounts_page.refresh()
        self.settings_page.refresh()

    def _show_error(self, code):
        self._error_code = code
        key = 'error.' + code
        self.error_label.setText(
            self.tr.text(key if key in CATALOG[self.tr.language] else 'error.generic')
        )
        self.error_label.setToolTip(code)
        self.error_label.show()

    def _select_dialog(self, identity, selection):
        if selection is None:
            self._show_error('selection_refresh_required')
            return
        dialog = QDialog(self)
        self.tr.bind(dialog, 'select_lesson', setter='setWindowTitle')
        dialog.resize(520, 350)
        layout = QVBoxLayout(dialog)
        layout.addWidget(self.tr.widget(QLabel, 'select_materials'))
        items = QListWidget()
        layout.addWidget(items)
        for number, code in enumerate(selection.ids):
            title = (
                selection.titles[number]
                if number < len(selection.titles)
                else self.tr.text('video_number', number=number + 1)
            )
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, code)
            item.setCheckState(Qt.CheckState.Checked)
            items.addItem(item)
            if number >= len(selection.titles):
                self.tr.bind(item, 'video_number', number=number + 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        layout.addWidget(buttons)
        self.tr.bind(buttons.button(QDialogButtonBox.StandardButton.Cancel), 'cancel')
        self.tr.bind(buttons.button(QDialogButtonBox.StandardButton.Ok), 'ok')
        buttons.rejected.connect(dialog.reject)

        def accept():
            ids = tuple(
                items.item(n).data(Qt.ItemDataRole.UserRole)
                for n in range(items.count())
                if items.item(n).checkState() == Qt.CheckState.Checked
            )
            if ids:
                self.presenter.select_items(identity, ids)
                dialog.accept()

        buttons.accepted.connect(accept)
        self._track_dialog(dialog)
        dialog.open()

    def _source_dialog(self, identity):
        dialog = QInputDialog(self)
        self.tr.bind(dialog, 'restore_source', setter='setWindowTitle')
        self.tr.bind(dialog, 'original_link', setter='setLabelText')
        self.tr.bind(dialog, 'cancel', setter='setCancelButtonText')
        self.tr.bind(dialog, 'ok', setter='setOkButtonText')
        dialog.setInputMode(QInputDialog.InputMode.TextInput)
        dialog.textValueSelected.connect(lambda text: self.presenter.provide_source(identity, text))
        self._track_dialog(dialog)
        dialog.open()

    def _shutdown_finished(self):
        if self._closing_requested:
            self.close()

    def dispose_ui(self):
        if self._ui_disposed:
            return
        self._ui_disposed = True
        QApplication.instance().removeEventFilter(self._input_actions)
        self.theme.close()
        self.tr.close()

    def closeEvent(self, event):
        self._closing_requested = True
        self.dispose_ui()
        for dialog in tuple(self._dialogs):
            dialog.reject()
        self.presenter.shutdown()
        if self.presenter.is_closed:
            event.accept()
        else:
            self.setEnabled(False)
            event.ignore()
