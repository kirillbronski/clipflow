"""The line above the queue: kind tabs, status menu, item count, search and sorting."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from clipflow.ui.i18n import Translator
from clipflow.ui.queue_toolbar import QueueToolbar


@pytest.fixture
def toolbar(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    bar = QueueToolbar(Translator('ru'), host)
    host.resize(900, 60)
    host.show()
    yield bar  # the host must outlive the test, or Qt deletes the toolbar with it
    host.close()


def test_kind_tabs_emit_and_check_one(toolbar):
    seen = []
    toolbar.kind_changed.connect(seen.append)
    assert [b.text() for b in toolbar.kind_buttons.values()] == [
        'Все',
        'Видео',
        'Аудио',
        'Фото',
        'Плейлисты',
    ]
    toolbar.kind_buttons['audio'].click()
    assert seen == ['audio']
    assert [k for k, b in toolbar.kind_buttons.items() if b.isChecked()] == ['audio']


def test_status_menu_shows_counts_and_emits(toolbar):
    seen = []
    toolbar.status_changed.connect(seen.append)
    toolbar.set_counts({'all': 12, 'active': 3, 'completed': 8, 'failed': 1})
    assert toolbar.status_actions['active'].text() == 'В работе  3'
    assert toolbar.status_button.text() == 'Все  12 ▾'
    toolbar.status_actions['failed'].trigger()
    assert seen == ['failed']
    assert toolbar.status_button.text() == 'Ошибки  1 ▾'
    assert toolbar.status_actions['failed'].isChecked()
    assert not toolbar.status_actions['all'].isChecked()


@pytest.mark.parametrize(
    ('language', 'count', 'text'),
    [
        ('ru', 1, '1 элемент'),
        ('ru', 2, '2 элемента'),
        ('ru', 5, '5 элементов'),
        ('ru', 21, '21 элемент'),
        ('en', 1, '1 item'),
        ('en', 5, '5 items'),
    ],
)
def test_items_label_plural(qtbot, language, count, text):
    bar = QueueToolbar(Translator(language))
    qtbot.addWidget(bar)
    bar.set_visible_count(count)
    assert bar.items_label.text() == text


def test_search_opens_filters_and_escape_clears(toolbar, qtbot):
    seen = []
    toolbar.query_changed.connect(seen.append)
    assert not toolbar.search_field.isVisible()
    toolbar.open_search()
    assert toolbar.search_field.isVisible()
    assert toolbar.search_field.placeholderText() == 'Поиск по названию, автору и ссылке'
    toolbar.search_field.insert('ёлка')  # QTest.keyClicks aborts on Cyrillic
    assert seen[-1] == 'ёлка'
    qtbot.keyClick(toolbar.search_field, Qt.Key.Key_Escape)
    assert toolbar.search_field.text() == ''
    assert not toolbar.search_field.isVisible()
    assert seen[-1] == ''


def test_search_with_text_stays_open_on_focus_loss(toolbar, qtbot):
    toolbar.open_search()
    toolbar.search_field.setText('x')
    toolbar.close_search(only_if_empty=True)
    assert toolbar.search_field.isVisible()
    toolbar.search_field.setText('')
    toolbar.close_search(only_if_empty=True)
    assert not toolbar.search_field.isVisible()


def test_sort_menu_emits_key_and_direction(toolbar):
    seen = []
    toolbar.sort_changed.connect(lambda key, descending: seen.append((key, descending)))
    assert toolbar.sort_actions['added'].isChecked()
    toolbar.sort_actions['size'].trigger()
    assert seen[-1] == ('size', False)
    assert toolbar.sort_actions['size'].isChecked()
    assert not toolbar.sort_actions['added'].isChecked()
    toolbar.descending_action.trigger()
    assert seen[-1] == ('size', True)
    texts = [a.text() for a in toolbar.sort_menu.actions() if a.text()]
    assert texts[-1] == 'Порядок загрузки не меняется'
    note = toolbar.sort_menu.actions()[-1]
    assert not note.isEnabled()


def test_sort_and_search_buttons_highlight_when_active(toolbar):
    assert not toolbar.sort_button.property('active')
    toolbar.sort_actions['title'].trigger()
    assert toolbar.sort_button.property('active')
    toolbar.sort_actions['added'].trigger()
    assert not toolbar.sort_button.property('active')
    toolbar.open_search()
    toolbar.search_field.setText('a')
    assert toolbar.search_button.property('active')


def test_texts_follow_language(qtbot):
    translator = Translator('ru')
    bar = QueueToolbar(translator)
    qtbot.addWidget(bar)
    bar.set_counts({'all': 2, 'active': 1, 'completed': 1, 'failed': 0})
    bar.set_visible_count(2)
    translator.set_language('en')
    assert bar.kind_buttons['photo'].text() == 'Photos'
    assert bar.items_label.text() == '2 items'
    assert bar.status_button.text() == 'All  2 ▾'
    assert bar.sort_actions['duration'].text() == 'Duration'
