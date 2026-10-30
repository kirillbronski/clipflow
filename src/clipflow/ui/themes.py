"""One application palette and semantic tokens. Service changes only small accents."""

import sys
from pathlib import Path
from types import MappingProxyType

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPalette, QPixmap

PALETTES = {
    'dark': dict(
        background='#1b1c23',
        surface='#23252e',
        sidebar='#17181f',
        hover='#30323e',
        text='#f4f3fa',
        muted='#b8b6c8',
        disabled='#aaa6bb',
        border='#383b49',
        accent='#b6a4ff',
        accent_text='#181420',
        success='#80d4b1',
        error='#ffaaa5',
        selection='#58467f',
        selection_text='#ffffff',
        focus='#b6a4ff',
        menu='#24262f',
        dialog='#24262f',
        youtube='#ff8a86',
        instagram='#c0a4ff',
        getcourse='#80d4b1',
    ),
    'light': dict(
        background='#ffffff',
        surface='#f6f7fa',
        sidebar='#f5f6f9',
        hover='#eeedf8',
        text='#26272e',
        muted='#626a7e',
        disabled='#626a7e',
        border='#e4e7ef',
        accent='#6253da',
        accent_text='#ffffff',
        success='#126444',
        error='#a51b28',
        selection='#eeebfd',
        selection_text='#5141b7',
        focus='#6253da',
        menu='#ffffff',
        dialog='#ffffff',
        youtube='#bc2b36',
        instagram='#6952d9',
        getcourse='#15715c',
    ),
}
TEXT_PAIRS = tuple(
    (fg, bg)
    for fg in ('text', 'muted', 'disabled', 'success', 'error')
    for bg in ('background', 'surface', 'sidebar', 'hover', 'menu', 'dialog')
) + (
    ('selection_text', 'selection'),
    ('accent_text', 'accent'),
    ('accent_text', 'youtube'),
    ('accent_text', 'instagram'),
    ('accent_text', 'getcourse'),
    ('youtube', 'surface'),
    ('instagram', 'surface'),
    ('getcourse', 'surface'),
)


def application_icon():
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[3]))
    return QIcon(str(root / 'assets/icons/clipflow.png'))


def glyph_icon(glyph, color, size=16):
    """Draw a text glyph as an icon so button labels stay words only."""
    scale = 2
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.setDevicePixelRatio(scale)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    font = QFont()
    font.setPixelSize(size - 2)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor(color))
    painter.drawText(0, 0, size, size, Qt.AlignmentFlag.AlignCenter, glyph)
    painter.end()
    return QIcon(pixmap)


class ThemeManager(QObject):
    changed = Signal()

    def __init__(self, app, settings, parent=None):
        super().__init__(parent)
        self.app = app
        self.mode = settings.theme
        scheme = app.styleHints().colorScheme()
        self._system = 'dark' if scheme == Qt.ColorScheme.Dark else 'light'
        app.setStyle('Fusion')
        app.styleHints().colorSchemeChanged.connect(self._system_changed)
        self._apply()

    def resolved_mode(self):
        return self._system if self.mode == 'system' else self.mode

    def tokens(self):
        return MappingProxyType(PALETTES[self.resolved_mode()])

    def set_mode(self, mode):
        if mode not in {'dark', 'light', 'system'}:
            raise ValueError('invalid_theme')
        if self.mode != mode:
            self.mode = mode
            self._apply()

    def _system_changed(self, scheme):
        if scheme == Qt.ColorScheme.Unknown:
            return
        self._system = 'dark' if scheme == Qt.ColorScheme.Dark else 'light'
        if self.mode == 'system':
            self._apply()

    def close(self):
        self.app.styleHints().colorSchemeChanged.disconnect(self._system_changed)

    def _apply(self):
        t = self.tokens()
        palette = QPalette()
        roles = {
            'Window': 'background',
            'Base': 'background',
            'AlternateBase': 'surface',
            'WindowText': 'text',
            'Text': 'text',
            'Button': 'surface',
            'ButtonText': 'text',
            'Highlight': 'selection',
            'HighlightedText': 'selection_text',
            'ToolTipBase': 'menu',
            'ToolTipText': 'text',
            'PlaceholderText': 'muted',
            'Link': 'focus',
            'BrightText': 'text',
        }
        for role, key in roles.items():
            palette.setColor(getattr(QPalette.ColorRole, role), QColor(t[key]))
        for role in ('WindowText', 'Text', 'ButtonText', 'PlaceholderText'):
            palette.setColor(
                QPalette.ColorGroup.Disabled,
                getattr(QPalette.ColorRole, role),
                QColor(t['disabled']),
            )
        self.app.setPalette(palette)
        self.app.setStyleSheet(styles(t))
        self.changed.emit()


def styles(t):
    return """
QWidget {{ color: {text}; font-family: "{font_family}"; font-size: 13px; font-weight: 400; }}
QMainWindow,QWidget#root {{ background: {background}; }}
QFrame#sidebar {{ background: {sidebar}; border-right: 1px solid {border}; }}
QFrame#composer {{ background: {surface}; border: 1px solid {border}; border-radius: 10px; }}
QWidget#composerSection,QLabel {{ background: transparent; }}
QLabel#muted {{ color: {muted}; font-size: 12px; }}
QLabel#heading {{ font-size: 25px; font-weight: 700; }}
QLabel#brand {{ font-size: 20px; font-weight: 700; padding: 8px; }}
QFrame#divider {{ background: {border}; border: none; }}
QLabel#error {{ color: {error}; }}
QPushButton {{ background: {surface}; border: 1px solid {border}; border-radius: 7px; padding: 8px 10px; }}
QPushButton:hover {{ background: {hover}; }}
QPushButton:focus,QLineEdit:focus,QComboBox:focus,QPlainTextEdit:focus,QListView:focus,QToolButton:focus {{ border: 2px solid {focus}; }}
QPushButton:disabled,QToolButton:disabled,QComboBox:disabled,QCheckBox:disabled {{ color: {disabled}; }}
QPushButton#primary {{ background: {accent}; color: {accent_text}; border-color: {accent}; font-weight: 600; }}
QPushButton#nav {{ text-align: left; background: transparent; border: none; padding: 11px; }}
QPushButton#nav:checked,QPushButton#mode:checked {{ background: {selection}; color: {selection_text}; }}
QPushButton#mode {{ background: transparent; border: none; color: {muted}; padding: 8px 12px; font-size: 12px; }}
QPushButton#mode:checked {{ background: {background}; color: {text}; font-weight: 600; }}
QPushButton#inlinePaste {{ background: transparent; border: none; color: {muted}; padding: 2px 7px; font-size: 11px; }}
QPushButton#statusTab {{ background: transparent; border: none; border-bottom: 2px solid transparent; border-radius: 0; color: {muted}; font-size: 11px; padding: 9px 3px; }}
QPushButton#statusTab:checked {{ color: {text}; border-bottom-color: {accent}; }}
QToolButton {{ background: transparent; border: 1px solid transparent; color: {muted}; padding: 4px; }}
QLineEdit,QComboBox,QPlainTextEdit,QTextEdit {{ background: {background}; border: 1px solid {border}; border-radius: 6px; padding: 10px; color: {text}; placeholder-text-color: {muted}; selection-background-color: {selection}; selection-color: {selection_text}; }}
QComboBox QAbstractItemView,QListView,QListWidget,QTableView {{ background: {background}; color: {text}; alternate-background-color: {surface}; border: 1px solid {border}; selection-background-color: {selection}; selection-color: {selection_text}; outline: none; }}
QHeaderView::section {{ background: {surface}; color: {text}; padding: 4px; border: 1px solid {border}; }}
QListView#queue {{ border: none; }}
QScrollArea {{ background: {background}; border: none; }}
QScrollBar:vertical {{ background: {background}; width: 9px; }}
QScrollBar::handle:vertical {{ background: {border}; min-height: 30px; border-radius: 4px; }}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {{ height: 0; }}
QDialog,QMessageBox {{ background: {dialog}; }}
QMenuBar,QMenu {{ background: {menu}; color: {text}; }}
QMenu::item:selected,QMenuBar::item:selected {{ background: {selection}; color: {selection_text}; }}
QMenu::item:disabled {{ color: {disabled}; }}
QToolTip {{ background: {menu}; color: {text}; border: 1px solid {border}; }}
""".format(**t, font_family='Helvetica Neue' if sys.platform == 'darwin' else 'Segoe UI')
