"""Left column: brand, source navigation with live counts, accounts and settings."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from clipflow.domain.models import JobState
from clipflow.ui.themes import application_icon

_HISTORY_STATES = {JobState.COMPLETED, JobState.CANCELLED, JobState.FAILED}
_SOURCES = {'youtube', 'instagram', 'getcourse'}
NAVIGATION = (
    ('all_downloads', None, False),
    ('history', None, True),
    ('YouTube', 'youtube', False),
    ('Instagram', 'instagram', False),
    ('GetCourse', 'getcourse', False),
)


class NavigationButton(QPushButton):
    """Keep native button accessibility; paint a separate live count at the right."""

    count = None

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.count is not None:
            painter = QPainter(self)
            painter.setPen(self.palette().color(self.foregroundRole()))
            font = self.font()
            font.setPixelSize(11)
            painter.setFont(font)
            painter.drawText(
                self.rect().adjusted(0, 0, -12, 0),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                str(self.count),
            )


class Sidebar(QFrame):
    navigate = Signal(object, bool, str)  # service value or None, history, navigation key
    section = Signal(str)

    def __init__(self, translator, parent=None):
        super().__init__(parent)
        self.tr = translator
        self.setObjectName('sidebar')
        self.setFixedWidth(205)
        side = QVBoxLayout(self)
        side.setContentsMargins(14, 22, 14, 20)
        side.setSpacing(8)
        side.addLayout(self._brand())
        side.addSpacing(20)
        self.nav_buttons = []
        for key, service, history in NAVIGATION:
            if service == 'youtube':
                side.addSpacing(22)
                side.addWidget(self._sources_label())
            side.addWidget(self._nav_button(key, service, history))
        self.nav_buttons[0].setChecked(True)
        side.addStretch()
        self.accounts_button = self._section_button('accounts', 'accounts')
        side.addWidget(self.accounts_button)
        self.settings_button = self._section_button('menu_settings', 'settings')
        side.addWidget(self.settings_button)
        side.addSpacing(14)
        line = QFrame()
        line.setObjectName('divider')
        line.setFixedHeight(1)
        side.addWidget(line)
        local = self.tr.widget(QLabel, 'local_note')
        local.setObjectName('muted')
        side.addWidget(local)

    @staticmethod
    def _brand():
        row = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(application_icon().pixmap(32, 32))
        row.addWidget(logo)
        brand = QLabel('ClipFlow')
        brand.setObjectName('brand')
        row.addWidget(brand)
        row.addStretch()
        return row

    def _sources_label(self):
        sources = self.tr.widget(QLabel, 'sources_label')
        sources.setObjectName('muted')
        caps = sources.font()
        caps.setCapitalization(QFont.Capitalization.AllUppercase)
        caps.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2)
        sources.setFont(caps)
        return sources

    def _nav_button(self, key, service, history):
        button = NavigationButton(key) if service else self.tr.widget(NavigationButton, key)
        button.setProperty('nav_key', key)
        button.setObjectName('nav')
        button.setCheckable(True)
        button.clicked.connect(
            lambda checked=False, s=service, h=history, k=key: self.navigate.emit(s, h, k)
        )
        self.nav_buttons.append(button)
        return button

    def _section_button(self, key, section):
        button = self.tr.widget(QPushButton, key)
        button.setObjectName('nav')
        button.setCheckable(True)
        button.clicked.connect(lambda: self.section.emit(section))
        return button

    def set_compact(self, compact):
        self.setFixedWidth(180 if compact else 205)

    def select(self, nav_key=None, section=None):
        """Check exactly the chosen navigation entry or section button."""
        for button in self.nav_buttons:
            button.setChecked(button.property('nav_key') == nav_key)
        self.accounts_button.setChecked(section == 'accounts')
        self.settings_button.setChecked(section == 'settings')

    def set_counts(self, jobs):
        for button in self.nav_buttons:
            key = button.property('nav_key')
            button.count = sum(
                key == 'all_downloads'
                or key == 'history'
                and j.state in _HISTORY_STATES
                or j.request.link.service.value == key.lower()
                for j in jobs
            )
            button.update()

    def paint_sources(self, tokens):
        """Each source gets a dot and a checked tint in its own colour."""
        for button in self.nav_buttons:
            service = button.property('nav_key').lower()
            if service not in _SOURCES:
                continue
            dot = QPixmap(10, 10)
            dot.fill(Qt.GlobalColor.transparent)
            painter = QPainter(dot)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(QColor(tokens[service]))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(1, 1, 8, 8)
            painter.end()
            button.setIcon(QIcon(dot))
            tint = QColor(tokens[service])
            tint.setAlpha(22)
            button.setStyleSheet(
                f'QPushButton:checked {{color:{tokens[service]};'
                f'background:{tint.name(QColor.NameFormat.HexArgb)};}}'
            )
