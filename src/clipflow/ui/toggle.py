"""An on/off switch for settings, painted from the current theme like the queue rows."""

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QAbstractButton

from clipflow.ui.themes import PALETTES


class ToggleSwitch(QAbstractButton):
    def __init__(self, parent=None, *, theme=None):
        super().__init__(parent)
        self.theme = theme
        self.setCheckable(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(self.sizeHint())

    def sizeHint(self):
        return QSize(36, 20)

    def paintEvent(self, event):
        # Tokens are read on every paint so a theme switch shows at once.
        t = self.theme.tokens() if self.theme else PALETTES['dark']
        on = self.isChecked()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(t['accent'] if on else t['border']))
        painter.drawRoundedRect(QRectF(0, 0, 36, 20), 10, 10)
        painter.setBrush(QColor(t['accent_text'] if on else t['text']))
        painter.drawEllipse(QRectF(18 if on else 2, 2, 16, 16))
        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QColor(t['accent']))
            painter.drawRoundedRect(QRectF(0.5, 0.5, 35, 19), 9.5, 9.5)
        painter.end()
