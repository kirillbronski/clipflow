"""Native Qt editing and context menus, including Cyrillic-layout command keys."""

from PySide6.QtCore import QObject, QEvent, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QLineEdit, QPlainTextEdit, QTextEdit, QMenu

EDITORS = (QLineEdit, QPlainTextEdit, QTextEdit)
COMMANDS = {'ф': 'selectAll', 'с': 'copy', 'ч': 'cut', 'м': 'paste', 'я': 'undo', 'н': 'redo'}


class InputActions(QObject):
    def __init__(self, window, translator):
        super().__init__(window)
        self.window = window
        self.tr = translator
        self.primary = QKeySequence(QKeySequence.StandardKey.Paste)[0].keyboardModifiers()

    def owns(self, widget):
        current = widget
        while current is not None:
            if current is self.window:
                return True
            current = current.parent()
        return False

    def eventFilter(self, widget, event):
        if event.type() not in {
            QEvent.Type.ContextMenu,
            QEvent.Type.KeyPress,
            QEvent.Type.ShortcutOverride,
        }:
            return False
        if not isinstance(widget, EDITORS) or not self.owns(widget):
            return False
        if event.type() == QEvent.Type.ContextMenu:
            menu = self.menu(widget)
            widget._edit_menu = menu
            menu.aboutToHide.connect(menu.deleteLater)
            menu.popup(event.globalPos())
            return True
        modifier = self.primary
        if event.type() in {
            QEvent.Type.KeyPress,
            QEvent.Type.ShortcutOverride,
        } and event.modifiers() in {modifier, modifier | Qt.KeyboardModifier.ShiftModifier}:
            letter = chr(event.key()).lower() if 0 <= event.key() <= 0x10FFFF else ''
            command = COMMANDS.get(letter)
            if command:
                if event.type() == QEvent.Type.KeyPress:
                    if command == 'undo' and event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                        command = 'redo'
                    if command in {'selectAll', 'copy'} or not widget.isReadOnly():
                        getattr(widget, command)()
                event.accept()
                return True
        return False

    def menu(self, widget):
        menu = QMenu(widget)
        selected = (
            widget.hasSelectedText()
            if isinstance(widget, QLineEdit)
            else widget.textCursor().hasSelection()
        )
        editable = not widget.isReadOnly()
        undo = (
            widget.isUndoAvailable()
            if isinstance(widget, QLineEdit)
            else widget.document().isUndoAvailable()
        )
        redo = (
            widget.isRedoAvailable()
            if isinstance(widget, QLineEdit)
            else widget.document().isRedoAvailable()
        )
        for key, method, standard, enabled in [
            ('undo', 'undo', 'Undo', editable and undo),
            ('redo', 'redo', 'Redo', editable and redo),
            ('cut', 'cut', 'Cut', editable and selected),
            ('copy', 'copy', 'Copy', selected),
            ('paste', 'paste', 'Paste', editable),
            ('select_all', 'selectAll', 'SelectAll', True),
        ]:
            action = menu.addAction(self.tr.text(key))
            action.setData(key)
            action.setShortcut(QKeySequence(getattr(QKeySequence.StandardKey, standard)))
            action.setEnabled(enabled)
            action.triggered.connect(getattr(widget, method))
        return menu
