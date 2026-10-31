"""The window's menu bar, built once; texts are bound to the translator."""

from PySide6.QtGui import QActionGroup, QKeySequence
from PySide6.QtWidgets import QApplication


def build_menus(window):
    """Native menu bar: downloads, edit, view and settings; actions follow the language."""
    bar = window.menuBar()
    bar.setNativeMenuBar(True)
    downloads = window.downloads_menu = bar.addMenu('')
    window.tr.bind(downloads, 'menu_downloads', setter='setTitle')
    action = downloads.addAction('')
    window.tr.bind(action, 'batch')
    action.setShortcuts(QKeySequence.keyBindings(QKeySequence.StandardKey.New))
    action.triggered.connect(window._open_batch)
    window.addAction(action)
    action = downloads.addAction('')
    window.tr.bind(action, 'start_queue')
    action.triggered.connect(window.presenter.start_queue)
    downloads.addSeparator()
    for key, command in [
        ('cancel_queue', window.presenter.cancel_queue),
        ('clear_all', window._confirm_clear_all),
        ('clear_queue', window.presenter.clear_queue),
        ('clear_history', window.presenter.clear_history),
    ]:
        action = downloads.addAction('')
        window.tr.bind(action, key)
        if key in {'clear_queue', 'clear_history'}:
            window.tr.bind(action, 'keeps_files_hint', setter='setToolTip')
        action.triggered.connect(command)
    downloads.setToolTipsVisible(True)
    edit = bar.addMenu('')
    window.tr.bind(edit, 'menu_edit', setter='setTitle')
    for key, method, standard in [
        ('undo', 'undo', 'Undo'),
        ('redo', 'redo', 'Redo'),
        ('cut', 'cut', 'Cut'),
        ('copy', 'copy', 'Copy'),
        ('paste', 'paste', 'Paste'),
        ('select_all', 'selectAll', 'SelectAll'),
    ]:
        action = edit.addAction('')
        window.tr.bind(action, key)
        action.setShortcuts(QKeySequence.keyBindings(getattr(QKeySequence.StandardKey, standard)))
        window.addAction(action)
        action.triggered.connect(lambda checked=False, m=method: _edit(window, m))
    edit.aboutToShow.connect(lambda: _edit_enabled(window, edit))
    view = bar.addMenu('')
    window.tr.bind(view, 'menu_view', setter='setTitle')
    themes = view.addMenu('')
    window.tr.bind(themes, 'theme', setter='setTitle')
    window.theme_actions = {}
    group = QActionGroup(window)
    for mode in ('dark', 'light', 'system'):
        action = themes.addAction('')
        window.tr.bind(action, mode)
        action.setCheckable(True)
        group.addAction(action)
        window.theme_actions[mode] = action
        action.triggered.connect(lambda checked=False, m=mode: _preferences(window, theme=m))
    settings = bar.addMenu('')
    window.tr.bind(settings, 'menu_settings', setter='setTitle')
    languages = settings.addMenu('')
    window.tr.bind(languages, 'language', setter='setTitle')
    window.language_actions = {}
    group = QActionGroup(window)
    for code, label in [('ru', 'Русский'), ('en', 'English')]:
        action = languages.addAction(label)
        action.setCheckable(True)
        group.addAction(action)
        window.language_actions[code] = action
        action.triggered.connect(lambda checked=False, c=code: _preferences(window, language=c))
    # Explicit wrappers keep the native menu/language-binding lifetime clear.
    window._menu_objects = [downloads, edit, view, themes, settings, languages]


def _edit(window, method):
    widget = QApplication.focusWidget()
    if widget is not None and window._input_actions.owns(widget) and hasattr(widget, method):
        getattr(widget, method)()


def _edit_enabled(window, menu):
    widget = QApplication.focusWidget()
    for action in menu.actions():
        action.setEnabled(widget is not None and hasattr(widget, 'paste'))


def _preferences(window, **values):
    window.presenter.update_preferences(**values)
    window._settings_changed()  # Also roll back checkmarks if persistence failed.
