"""Preferences use the same validated owner-thread commands as the main menus."""

from PySide6.QtWidgets import QComboBox, QFormLayout, QLabel, QVBoxLayout, QWidget

from clipflow.version import APP_VERSION


class SettingsPage(QWidget):
    def __init__(self, presenter, translator, parent=None):
        super().__init__(parent)
        self.presenter = presenter
        self.tr = translator
        self._loading = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        form = QFormLayout()
        self.theme_box = QComboBox()
        self.language_box = QComboBox()
        for mode in ('dark', 'light', 'system'):
            self.theme_box.addItem(self.tr.text(mode), mode)
        for name, code in [('Русский', 'ru'), ('English', 'en')]:
            self.language_box.addItem(name, code)
        form.addRow(self.tr.widget(QLabel, 'theme'), self.theme_box)
        form.addRow(self.tr.widget(QLabel, 'language'), self.language_box)
        layout.addLayout(form)
        layout.addSpacing(24)
        layout.addWidget(self.tr.widget(QLabel, 'about'))
        self.about_label = QLabel(f'ClipFlow {APP_VERSION} · Preview')
        layout.addWidget(self.about_label)
        note = self.tr.widget(QLabel, 'about_description')
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()
        self.theme_box.currentIndexChanged.connect(
            lambda: self._save('theme', self.theme_box.currentData())
        )
        self.language_box.currentIndexChanged.connect(
            lambda: self._save('language', self.language_box.currentData())
        )
        presenter.settings_changed.connect(self.refresh)
        self.tr.changed.connect(self.refresh)
        self.refresh()

    def _save(self, key, value):
        if not self._loading:
            self.presenter.update_preferences(**{key: value})
            self.refresh()

    def refresh(self):
        self._loading = True
        for index, mode in enumerate(('dark', 'light', 'system')):
            self.theme_box.setItemText(index, self.tr.text(mode))
        self.theme_box.setCurrentIndex(self.theme_box.findData(self.presenter.settings.theme))
        self.language_box.setCurrentIndex(
            self.language_box.findData(self.presenter.settings.language)
        )
        self._loading = False
