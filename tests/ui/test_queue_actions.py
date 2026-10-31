"""Queue action labels, the Downloads menu and the icons drawn for button glyphs."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from tests.support.workbench import add, batch

TEXTS = {
    'ru': {
        'start_button': 'Скачать всё',
        'cancel_queue_button': 'Остановить всё',
        'clear_all_button': 'Очистить…',
        'add_button': 'Добавить в очередь',
        'batch_button': 'Несколько ссылок',
    },
    'en': {
        'start_button': 'Download all',
        'cancel_queue_button': 'Stop all',
        'clear_all_button': 'Clear…',
        'add_button': 'Add to queue',
        'batch_button': 'Multiple links',
    },
}
MENU = {
    'ru': (('Убрать незавершённые', 'Убрать завершённые'), 'Файлы на диске останутся'),
    'en': (('Remove unfinished', 'Remove finished'), 'Files on disk are kept'),
}


def button(window, name):
    return window.composer.add_button if name == 'add_button' else getattr(window, name)


def downloads_menu(window):
    return window.downloads_menu


@pytest.mark.parametrize('language', ['ru', 'en'])
def test_queue_buttons_and_menu_texts(make_window, language):
    window, _ = make_window()
    window.tr.set_language(language)
    for name, text in TEXTS[language].items():
        assert button(window, name).text() == text
    menu = downloads_menu(window)
    labels, hint = MENU[language]
    actions = {action.text(): action for action in menu.actions()}
    for label in labels:
        assert actions[label].toolTip() == hint
    assert menu.toolTipsVisible()


def test_buttons_use_icons_not_glyph_text(make_window):
    window, _ = make_window()
    for name in ('start_button', 'add_button', 'batch_button'):
        widget = button(window, name)
        assert not widget.icon().isNull(), name
        assert not set('▷↓+') & set(widget.text()), name
    assert all(not set('▷↓+') & set(action.text()) for action in downloads_menu(window).actions())


def test_icons_follow_theme(make_window):
    window, _ = make_window()
    before = {n: button(window, n).icon().cacheKey() for n in ('start_button', 'add_button')}
    window.theme.set_mode('light' if window.theme.resolved_mode() == 'dark' else 'dark')
    after = {n: button(window, n).icon().cacheKey() for n in ('start_button', 'add_button')}
    assert all(before[n] != after[n] for n in before)


def test_batch_dialog_accept_text_has_no_icon(make_window, qtbot):
    window, _ = make_window()
    dialog = batch(window, qtbot)
    assert dialog.accept_button.text() == 'Добавить в очередь'
    assert dialog.accept_button.icon().isNull()
    dialog.reject()


def test_clear_all_confirmation_names_the_action_without_ellipsis(make_window, qtbot):
    window, _ = make_window()
    add(window, qtbot)
    qtbot.mouseClick(window.clear_all_button, Qt.MouseButton.LeftButton)
    box = window.findChild(QMessageBox)
    assert box.button(QMessageBox.StandardButton.Yes).text() == 'Очистить всё'
    box.button(QMessageBox.StandardButton.No).click()


def test_icon_never_makes_its_button_taller_than_its_neighbours(make_window):
    window, _ = make_window()
    row = (window.start_button, window.cancel_queue_button, window.clear_all_button)
    for widget in row:  # a text line shorter than a 16 px icon, as with some Windows fonts
        widget.setStyleSheet('font-size: 9px;')
    window._accent()
    assert len({widget.sizeHint().height() for widget in row}) == 1
