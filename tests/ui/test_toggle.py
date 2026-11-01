"""The settings switch: painted, keyboard-friendly, colours from the current theme."""

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor

from clipflow.ui.themes import PALETTES
from clipflow.ui.toggle import ToggleSwitch


class Theme:
    def __init__(self):
        self.palette = dict(PALETTES['dark'])

    def tokens(self):
        return self.palette


def test_click_toggles_once(qtbot):
    switch = ToggleSwitch()
    qtbot.addWidget(switch)
    seen = []
    switch.toggled.connect(seen.append)
    qtbot.mouseClick(switch, Qt.MouseButton.LeftButton)
    assert switch.isChecked()
    assert seen == [True]


def test_space_toggles(qtbot):
    switch = ToggleSwitch()
    qtbot.addWidget(switch)
    switch.show()
    switch.setFocus()
    qtbot.keyClick(switch, Qt.Key.Key_Space)
    assert switch.isChecked()


def test_size_is_fixed(qtbot):
    switch = ToggleSwitch()
    qtbot.addWidget(switch)
    assert switch.sizeHint() == QSize(36, 20)


def test_toggle_reads_theme_on_each_paint(qtbot):
    theme = Theme()
    switch = ToggleSwitch(theme=theme)
    qtbot.addWidget(switch)
    switch.resize(36, 20)
    switch.setChecked(True)

    def track():
        return switch.grab().toImage().pixelColor(4, 10)

    first = track()
    theme.palette['accent'] = '#00ff00'
    second = track()
    assert first != second
    assert second == QColor('#00ff00')
