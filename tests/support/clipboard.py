"""Clipboard gestures: shortcut and context-menu paste."""

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QContextMenuEvent, QKeySequence
from PySide6.QtWidgets import QApplication, QMenu


def paste_shortcut(qtbot, widget):
    widget.setFocus()
    qtbot.keySequence(widget, QKeySequence(QKeySequence.StandardKey.Paste))


def context_paste(qtbot, widget):
    point = QPoint(10, 10)
    QApplication.sendEvent(
        widget, QContextMenuEvent(QContextMenuEvent.Reason.Mouse, point, widget.mapToGlobal(point))
    )
    menu = QApplication.activePopupWidget()
    assert isinstance(menu, QMenu)
    action = next(action for action in menu.actions() if action.data() == 'paste')
    assert action.isEnabled()
    qtbot.mouseClick(menu, Qt.MouseButton.LeftButton, pos=menu.actionGeometry(action).center())
