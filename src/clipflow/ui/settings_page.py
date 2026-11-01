"""Settings in sections, as in 4K: the list on the left, the chosen section on the right.

A new preference is one add_choice/add_toggle line in its section; a section appears with its
first preference. Values are saved at once through the presenter, like the main menus.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from clipflow.ui.i18n import CATALOG
from clipflow.ui.toggle import ToggleSwitch
from clipflow.version import APP_VERSION

# Section key, its glyph and its title key; 'about' sits apart at the bottom of the list.
SECTIONS = (
    ('general', '⚙', 'settings_section.general'),
    ('accounts', '◉', 'settings_section.accounts'),
    ('about', 'ⓘ', 'settings_section.about'),
)


class SettingsPage(QWidget):
    def __init__(self, presenter, translator, parent=None, *, theme=None, accounts=None):
        super().__init__(parent)
        self.presenter = presenter
        self.tr = translator
        self.theme = theme
        self._loading = False
        self._refreshers = []
        self._pages = {}
        self._areas = {}
        self.section_buttons = {}
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(24)
        column = QVBoxLayout()
        column.setSpacing(4)
        sections = QWidget()
        sections.setFixedWidth(200)
        sections.setLayout(column)
        layout.addWidget(sections)
        right = QVBoxLayout()
        right.setSpacing(16)
        self.section_title = QLabel()
        self.section_title.setObjectName('sectionTitle')
        right.addWidget(self.section_title)
        self.stack = QStackedWidget()
        right.addWidget(self.stack, 1)
        layout.addLayout(right, 1)
        self._group = QButtonGroup(self)

        general = self._section('general')
        self.language_box = self.add_choice(
            general,
            'language',
            [('Русский', 'ru'), ('English', 'en')],
            lambda: self.presenter.settings.language,
            lambda value: self.presenter.update_preferences(language=value),
        )
        self.theme_box = self.add_choice(
            general,
            'theme',
            [('dark', 'dark'), ('light', 'light'), ('system', 'system')],
            lambda: self.presenter.settings.theme,
            lambda value: self.presenter.update_preferences(theme=value),
        )
        self.add_divider(general)
        self.auto_start_toggle = self.add_toggle(
            general,
            'auto_start_setting',
            'auto_start_hint',
            lambda: self.presenter.settings.auto_start,
            lambda value: self.presenter.set_auto_start(value),
        )
        self.smart_mode_toggle = self.add_toggle(
            general,
            'smart_mode',
            'smart_mode_hint',
            lambda: self.presenter.settings.smart_mode,
            lambda value: self.presenter.set_smart_mode(value),
        )
        if accounts is not None:
            self._section('accounts').layout().addWidget(accounts)
        about = self._section('about')
        self.about_label = QLabel(f'ClipFlow {APP_VERSION} · Preview')
        about.layout().addWidget(self.about_label)
        note = self.tr.widget(QLabel, 'about_description')
        note.setWordWrap(True)
        about.layout().addWidget(note)

        for key, *_ in SECTIONS:
            if key in self.section_buttons:
                if key == 'about':
                    column.addStretch()
                column.addWidget(self.section_buttons[key])
        for page in self._pages.values():
            page.layout().addStretch()
        self.current_section = None
        self.show_section('general')
        presenter.settings_changed.connect(self.refresh)
        self.tr.changed.connect(self.refresh)
        self.refresh()

    def _section(self, key):
        page = QWidget()
        content = QVBoxLayout(page)
        content.setContentsMargins(0, 0, 8, 0)
        content.setSpacing(10)
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setWidget(page)
        self.stack.addWidget(area)
        button = QPushButton()
        button.setObjectName('nav')
        button.setCheckable(True)
        button.clicked.connect(lambda: self.show_section(key))
        self._group.addButton(button)
        self.section_buttons[key] = button
        self._pages[key] = page
        self._areas[key] = area
        return page

    def show_section(self, key):
        self.current_section = key
        self.stack.setCurrentWidget(self._areas[key])
        self.section_buttons[key].setChecked(True)
        self._titles()

    def add_choice(self, page, label_key, items, getter, setter):
        """A labelled drop-down; item texts that are catalogue keys follow the language."""
        page.layout().addWidget(self.tr.widget(QLabel, label_key))
        box = QComboBox()
        box.setMinimumWidth(260)
        for _, value in items:
            box.addItem('', value)
        row = QHBoxLayout()
        row.addWidget(box)
        row.addStretch()
        page.layout().addLayout(row)

        def refresh():
            for index, (text, _) in enumerate(items):
                box.setItemText(index, self._label(text))
            box.setCurrentIndex(box.findData(getter()))

        box.currentIndexChanged.connect(lambda: self._save(setter, box.currentData()))
        self._refreshers.append(refresh)
        return box

    def add_toggle(self, page, label_key, hint_key, getter, setter):
        """A switch with its caption on the left and a muted hint below."""
        row = QHBoxLayout()
        label = self.tr.widget(QLabel, label_key)
        label.setWordWrap(True)
        row.addWidget(label, 1)
        switch = ToggleSwitch(theme=self.theme)
        row.addWidget(switch, 0, Qt.AlignmentFlag.AlignTop)
        page.layout().addLayout(row)
        hint = self.tr.widget(QLabel, hint_key)
        hint.setObjectName('muted')
        hint.setWordWrap(True)
        page.layout().addWidget(hint)
        switch.toggled.connect(lambda checked: self._save(setter, checked))
        self._refreshers.append(lambda: switch.setChecked(getter()))
        return switch

    @staticmethod
    def add_divider(page):
        line = QFrame()
        line.setObjectName('divider')
        line.setFixedHeight(1)
        page.layout().addSpacing(6)
        page.layout().addWidget(line)
        page.layout().addSpacing(6)
        return line

    def _label(self, text):
        return self.tr.text(text) if text in CATALOG[self.tr.language] else text

    def _save(self, setter, value):
        if not self._loading:
            setter(value)
            # A refused save shows the stored value again.
            self.refresh()

    def _titles(self):
        for key, glyph, title in SECTIONS:
            if key in self.section_buttons:
                self.section_buttons[key].setText(f'{glyph}   {self.tr.text(title)}')
        self.section_title.setText(
            self.tr.text(next(title for key, _, title in SECTIONS if key == self.current_section))
        )

    def refresh(self):
        self._loading = True
        for refresh in self._refreshers:
            refresh()
        self._titles()
        self._loading = False
