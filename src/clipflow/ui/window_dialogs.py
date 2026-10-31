"""Dialogs and the context menu of the main window; open dialogs are tracked on the window."""

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QVBoxLayout,
)

from clipflow.domain.models import TERMINAL_STATES, JobState
from clipflow.domain.urls import request_key
from clipflow.ui.batch_dialog import BatchDialog
from clipflow.ui.queue_model import JobListModel


class WindowDialogs:
    def __init__(self, window):
        self.window = window

    def open_batch(self):
        window = self.window
        for dialog in window._dialogs:
            if isinstance(dialog, BatchDialog) and dialog.isVisible():
                dialog.raise_()
                return
        if not window._commit_options():
            return
        existing = {request_key(job.request) for job in window.presenter.model.jobs}
        dialog = BatchDialog(
            window.presenter.submission,
            window.presenter.settings.presets,
            window.composer.limit_box.currentData(),
            window,
            existing_keys=existing,
            translator=window.tr,
        )

        def confirm(preview):
            result = window.presenter.submit_preview(preview)
            if result is not None:
                window.error_label.hide()
                if not result.added and result.existing:
                    window._show_error('already_queued')
                dialog.accept()

        dialog.confirmed.connect(confirm)
        self.track(dialog)
        dialog.open()

    def track(self, dialog):
        window = self.window
        window._dialogs.append(dialog)

        def finished(result):
            if dialog in window._dialogs:
                window._dialogs.remove(dialog)
            dialog.deleteLater()

        dialog.finished.connect(finished)

    def history_menu(self, position):
        window = self.window
        index = window.queue_view.indexAt(position)
        if not index.isValid():
            return
        if index.data(JobListModel.GroupRole) is not None:
            self.group_menu(index.data(JobListModel.JobIdRole), position)
            return
        if not window.queue_view.selectionModel().isSelected(index):
            window.queue_view.setCurrentIndex(index)
        identities = tuple(
            i.data(JobListModel.JobIdRole)
            for i in window.queue_view.selectionModel().selectedRows()
        )
        jobs = tuple(window.presenter.repository.get(identity) for identity in identities)
        menu = QMenu(window)
        action = menu.addAction(window.tr.text('open_folder'))
        action.triggered.connect(lambda: window.presenter.open_result(identities[0]))
        terminal = all(
            j.state in {JobState.COMPLETED, JobState.CANCELLED, JobState.FAILED} for j in jobs
        )
        action = menu.addAction(window.tr.text('repeat_job'))
        action.setEnabled(terminal)
        action.triggered.connect(
            lambda: [window.presenter.repeat_job(identity) for identity in identities]
        )
        menu.addSeparator()
        action = menu.addAction(window.tr.text('remove_list'))
        action.setEnabled(terminal and window.presenter.executor.is_idle)
        action.triggered.connect(lambda: window.presenter.remove_jobs(identities))
        action = menu.addAction(window.tr.text('delete_files'))
        action.setEnabled(
            terminal and window.presenter.executor.is_idle and any(j.result_files for j in jobs)
        )
        action.triggered.connect(lambda: self.confirm_delete(identities))
        menu.aboutToHide.connect(menu.deleteLater)
        menu.popup(window.queue_view.viewport().mapToGlobal(position))

    def group_menu(self, group_id, position=None):
        """Actions on a whole playlist or profile, at the cursor or under its row."""
        window = self.window
        presenter = window.presenter
        members = presenter.model.members(group_id)
        idle = presenter.executor.is_idle
        menu = QMenu(window)

        def add(key, slot, enabled=True):
            action = menu.addAction(window.tr.text(key))
            action.setEnabled(enabled)
            action.triggered.connect(slot)

        add(
            'group_menu.pause',
            lambda: presenter.pause_group(group_id),
            any(j.state not in TERMINAL_STATES and j.state != JobState.PAUSED for j in members),
        )
        add(
            'group_menu.resume',
            lambda: presenter.resume_group(group_id),
            any(j.state == JobState.PAUSED and j.pause_reason == 'user' for j in members),
        )
        add(
            'group_menu.retry_failed',
            lambda: presenter.retry_group_failures(group_id),
            any(
                j.state in {JobState.FAILED, JobState.CANCELLED} and not j.source_required
                for j in members
            ),
        )
        add('group_menu.open_folder', lambda: presenter.open_group_folder(group_id))
        menu.addSeparator()
        add('group_menu.remove', lambda: presenter.remove_group(group_id))
        add(
            'group_menu.delete_files',
            lambda: self.confirm_delete_group(group_id),
            idle
            and all(j.state in TERMINAL_STATES for j in members)
            and any(j.result_files for j in members),
        )
        menu.aboutToHide.connect(menu.deleteLater)
        view = window.queue_view
        if position is None:
            row = presenter.model._rows.get(group_id)
            index = window.queue_panel.proxy.mapFromSource(presenter.model.index(row))
            rect = view.visualRect(index)
            position = rect.topRight() + QPoint(-80, rect.height() // 2)
        menu.popup(view.viewport().mapToGlobal(position))

    def confirm_delete_group(self, group_id):
        members = self.window.presenter.model.members(group_id)
        self.confirm_delete(
            (group_id, *(j.id for j in members)),
            lambda: self.window.presenter.delete_group_files(group_id, True),
        )

    def confirm_clear_all(self):
        window = self.window
        count = len(window.presenter.repository.list())
        if not count:
            return
        dialog = QMessageBox(window)
        window.tr.bind(dialog, 'clear_all_confirm', setter='setWindowTitle')
        window.tr.bind(dialog, 'clear_all_confirmation', count=count)
        dialog.setIcon(QMessageBox.Icon.Warning)
        checkbox = window.tr.widget(QCheckBox, 'clear_all_delete_files')
        checkbox.setChecked(False)
        dialog.setCheckBox(checkbox)
        dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        dialog.setDefaultButton(QMessageBox.StandardButton.No)
        window.tr.bind(dialog.button(QMessageBox.StandardButton.Yes), 'clear_all_confirm')
        window.tr.bind(dialog.button(QMessageBox.StandardButton.No), 'cancel')
        dialog.finished.connect(
            lambda result: (
                window.presenter.clear_all(delete_files=checkbox.isChecked())
                if result == QMessageBox.StandardButton.Yes
                else None
            )
        )
        self.track(dialog)
        dialog.open()

    def confirm_delete(self, identities, delete=None):
        window = self.window
        jobs = tuple(window.presenter.repository.get(identity) for identity in identities)
        count = len({path for job in jobs for path in job.result_files})
        if not count:
            return
        dialog = QMessageBox(window)
        window.tr.bind(dialog, 'delete_files', setter='setWindowTitle')
        window.tr.bind(dialog, 'delete_confirmation', count=count)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        dialog.setDefaultButton(QMessageBox.StandardButton.No)
        window.tr.bind(dialog.button(QMessageBox.StandardButton.Yes), 'delete_files')
        window.tr.bind(dialog.button(QMessageBox.StandardButton.No), 'cancel')
        dialog.finished.connect(
            lambda result: (
                (delete or (lambda: window.presenter.delete_files(identities, True)))()
                if result == QMessageBox.StandardButton.Yes
                else None
            )
        )
        self.track(dialog)
        dialog.open()

    def select(self, identity, selection):
        window = self.window
        if selection is None:
            window._show_error('selection_refresh_required')
            return
        dialog = QDialog(window)
        window.tr.bind(dialog, 'select_lesson', setter='setWindowTitle')
        dialog.resize(520, 350)
        layout = QVBoxLayout(dialog)
        layout.addWidget(window.tr.widget(QLabel, 'select_materials'))
        items = QListWidget()
        layout.addWidget(items)
        for number, code in enumerate(selection.ids):
            title = (
                selection.titles[number]
                if number < len(selection.titles)
                else window.tr.text('video_number', number=number + 1)
            )
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, code)
            item.setCheckState(Qt.CheckState.Checked)
            items.addItem(item)
            if number >= len(selection.titles):
                window.tr.bind(item, 'video_number', number=number + 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        layout.addWidget(buttons)
        window.tr.bind(buttons.button(QDialogButtonBox.StandardButton.Cancel), 'cancel')
        window.tr.bind(buttons.button(QDialogButtonBox.StandardButton.Ok), 'ok')
        buttons.rejected.connect(dialog.reject)

        def accept():
            ids = tuple(
                items.item(n).data(Qt.ItemDataRole.UserRole)
                for n in range(items.count())
                if items.item(n).checkState() == Qt.CheckState.Checked
            )
            if ids:
                window.presenter.select_items(identity, ids)
                dialog.accept()

        buttons.accepted.connect(accept)
        self.track(dialog)
        dialog.open()

    def source(self, identity):
        window = self.window
        dialog = QInputDialog(window)
        window.tr.bind(dialog, 'restore_source', setter='setWindowTitle')
        window.tr.bind(dialog, 'original_link', setter='setLabelText')
        window.tr.bind(dialog, 'cancel', setter='setCancelButtonText')
        window.tr.bind(dialog, 'ok', setter='setOkButtonText')
        dialog.setInputMode(QInputDialog.InputMode.TextInput)
        dialog.textValueSelected.connect(
            lambda text: window.presenter.provide_source(identity, text)
        )
        self.track(dialog)
        dialog.open()
