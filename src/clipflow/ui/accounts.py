"""Account controls contain only status; credentials stay in protected gateway storage."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from clipflow.domain.models import Service
from clipflow.infrastructure.auth import BROWSERS
from clipflow.ui.composer import NAMES


class AccountsPage(QWidget):
    def __init__(self, presenter, translator, parent=None):
        super().__init__(parent)
        self.presenter = presenter
        self.tr = translator
        self.sign_in_buttons = {}
        self.logout_buttons = {}
        self.status_labels = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(18)
        note = self.tr.widget(QLabel, 'accounts_note')
        note.setWordWrap(True)
        layout.addWidget(note)
        for service in Service:
            row = QHBoxLayout()
            column = QVBoxLayout()
            column.addWidget(QLabel(NAMES[service]))
            status = QLabel()
            status.setTextFormat(Qt.TextFormat.PlainText)
            status.setWordWrap(True)
            column.addWidget(status)
            row.addLayout(column, 1)
            login = self.tr.widget(
                QPushButton, 'configure_access' if service == Service.GETCOURSE else 'sign_in'
            )
            logout = self.tr.widget(QPushButton, 'sign_out')
            self.status_labels[service] = status
            self.sign_in_buttons[service] = login
            self.logout_buttons[service] = logout
            login.clicked.connect(lambda checked=False, s=service: self._login(s))
            logout.clicked.connect(lambda checked=False, s=service: presenter.logout_account(s))
            row.addWidget(login)
            row.addWidget(logout)
            layout.addLayout(row)
        layout.addStretch()
        presenter.auth_changed.connect(self.refresh)
        self.tr.changed.connect(self.refresh)
        self.refresh()

    def _login(self, service):
        if service != Service.GETCOURSE:
            self.presenter.sign_in_account(service)
            return
        parent = self.window()
        dialog = GetCourseDialog(self.presenter, self.tr, parent.composer.url_input.text(), parent)
        parent._track_dialog(dialog)
        dialog.open()

    def refresh(self):
        gateway = self.presenter.auth_gateway
        for service in Service:
            status = gateway.status(service) if gateway else None
            saved = bool(status and status.connected)
            key = (
                'account_configured'
                if saved and service == Service.GETCOURSE
                else 'session_saved'
                if saved
                else 'not_signed_in'
            )
            text = self.tr.text(key)
            if status and status.account:
                text += ' · ' + status.account
            self.status_labels[service].setText(text)
            self.sign_in_buttons[service].setVisible(not saved or service == Service.GETCOURSE)
            self.sign_in_buttons[service].setEnabled(
                gateway is not None and not self.presenter._closing
            )
            self.logout_buttons[service].setVisible(saved)


class GetCourseDialog(QDialog):
    def __init__(self, presenter, translator, url='', parent=None):
        super().__init__(parent)
        self.presenter = presenter
        self.tr = translator
        self.tr.bind(self, 'configure_access', setter='setWindowTitle')
        self.resize(600, 480)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.school = QLineEdit(url)
        self.method = QComboBox()
        for key, value in [
            ('auth_email', 'email'),
            ('auth_cookies', 'cookies'),
            ('auth_browser', 'browser'),
        ]:
            self.method.addItem(self.tr.text(key), value)
        self.email = QLineEdit()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.file = QLineEdit()
        self.browser = QComboBox()
        for browser in BROWSERS:
            self.browser.addItem(
                {
                    'chrome': 'Google Chrome',
                    'edge': 'Microsoft Edge',
                    'opera_gx': 'Opera GX',
                    'yandex': 'Yandex Browser',
                }.get(browser, browser.title()),
                browser,
            )
        for key, widget in [
            ('school_lesson_url', self.school),
            ('access_method', self.method),
            ('email', self.email),
            ('password', self.password),
            ('cookies_file', self.file),
            ('browser', self.browser),
        ]:
            form.addRow(self.tr.widget(QLabel, key), widget)
        layout.addLayout(form)
        self.help = self.tr.widget(QLabel, 'school_scope_note')
        self.help.setWordWrap(True)
        layout.addWidget(self.help)
        row = QHBoxLayout()
        choose = self.tr.widget(QPushButton, 'choose')
        choose.clicked.connect(self._choose)
        previous = self.tr.widget(QPushButton, 'import_old_profile')
        self.tr.bind(previous, 'import_old_profile_hint', setter='setToolTip')
        previous.clicked.connect(self._import)
        row.addWidget(choose)
        row.addWidget(previous)
        row.addStretch()
        layout.addLayout(row)
        self.error = QLabel()
        self.error.setObjectName('error')
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        row = QHBoxLayout()
        row.addStretch()
        cancel = self.tr.widget(QPushButton, 'cancel')
        save = self.tr.widget(QPushButton, 'save')
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self._save)
        row.addWidget(cancel)
        row.addWidget(save)
        layout.addLayout(row)
        self.finished.connect(lambda result: self.password.clear())
        self.method.currentIndexChanged.connect(self._fields)
        self.tr.changed.connect(self._translate)
        self._fields()

    def _translate(self):
        for index, key in enumerate(('auth_email', 'auth_cookies', 'auth_browser')):
            self.method.setItemText(index, self.tr.text(key))

    def _fields(self):
        method = self.method.currentData()
        self.email.setEnabled(method == 'email')
        self.password.setEnabled(method == 'email')
        self.file.setEnabled(method == 'cookies')
        self.browser.setEnabled(method == 'browser')

    def _choose(self):
        file, _ = QFileDialog.getOpenFileName(self, self.tr.text('cookies_file'))
        if file:
            self.file.setText(file)

    def _save(self):
        result = self.presenter.configure_getcourse(
            self.school.text(),
            self.method.currentData(),
            email=self.email.text(),
            password=self.password.text(),
            file=self.file.text(),
            browser=self.browser.currentData(),
        )
        if result:
            self.password.clear()
            self.accept()
        else:
            self.error.setText(self.tr.text('error.auth_invalid_settings'))

    def _import(self):
        if self.presenter.import_getcourse(self.school.text()):
            self.accept()
        else:
            self.error.setText(self.tr.text('error.auth_invalid_school'))
