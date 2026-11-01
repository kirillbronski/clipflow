"""Quick settings chips in the download card mirror the card's own fields."""

from pathlib import Path

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

from clipflow.domain.models import Service
from clipflow.ui.quick_bar import FOLDER_WIDTH


def chip_items(chip):
    chip.menu().aboutToShow.emit()
    return [a.text() for a in chip.menu().actions() if a.text()]


def pick(chip, text):
    chip.menu().aboutToShow.emit()
    next(a for a in chip.menu().actions() if a.text() == text).trigger()


def test_chips_per_service(make_window):
    window, _ = make_window()
    composer = window.composer
    bar = composer.quick_bar
    composer.set_service(Service.YOUTUBE)
    assert bar.kind_chip.isVisible()
    assert bar.kind_chip.text() == composer.format_box.currentText()
    assert chip_items(bar.kind_chip) == [
        composer.format_box.itemText(i) for i in range(composer.format_box.count())
    ]
    composer.set_service(Service.INSTAGRAM)
    assert bar.kind_chip.text() == composer.filter_box.currentText()
    composer.set_service(Service.GETCOURSE)
    assert not bar.kind_chip.isVisible()


def test_chip_choice_sets_the_field_and_saves(make_window):
    window, _ = make_window()
    composer = window.composer
    composer.set_service(Service.YOUTUBE)
    bar = composer.quick_bar
    audio = composer.format_box.itemText(composer.format_box.findData('mp3'))
    pick(bar.kind_chip, audio)
    assert composer.format_box.currentData() == 'mp3'
    assert window.presenter.settings.presets[Service.YOUTUBE].format == 'mp3'
    assert not bar.quality_chip.isVisible()
    assert bar.kind_chip.text() == audio


def test_field_change_updates_chip(make_window):
    window, _ = make_window()
    composer = window.composer
    composer.set_service(Service.YOUTUBE)
    composer.format_box.setCurrentIndex(composer.format_box.findData('mkv'))
    assert composer.quick_bar.kind_chip.text() == 'MKV'


def test_chips_follow_service_change(make_window):
    window, _ = make_window()
    composer = window.composer
    composer.set_service(Service.INSTAGRAM)
    bar = composer.quick_bar
    photos = composer.filter_box.itemText(composer.filter_box.findData('photo'))
    pick(bar.kind_chip, photos)
    assert window.presenter.settings.presets[Service.INSTAGRAM].media_filter == 'photo'
    assert window.presenter.settings.presets[Service.YOUTUBE].media_filter == 'all'
    window.nav_buttons[2].click()  # YouTube in the sidebar
    assert bar.kind_chip.text() == composer.format_box.currentText()


def test_folder_chip_menu_and_tooltip(make_window, tmp_path, monkeypatch):
    window, _ = make_window()
    composer = window.composer
    bar = composer.quick_bar
    folder = Path(composer.folder_input.text())
    assert bar.folder_chip.toolTip() == str(folder)
    assert bar.folder_chip.text().endswith(folder.name)
    chosen = []
    monkeypatch.setattr(composer, '_choose_folder', lambda: chosen.append(True))
    pick(bar.folder_chip, window.tr.text('choose_folder_menu'))
    assert chosen == [True]


def test_folder_chip_long_path(make_window, tmp_path):
    window, _ = make_window()
    composer = window.composer
    deep = tmp_path.joinpath(
        *[f'уровень_{n}' for n in range(14)],
        ('Очень длинное имя итоговой папки для загрузок ' * 3).strip(),
    )
    deep.mkdir(parents=True)
    composer.folder_input.setText(str(deep))
    composer.folder_input.editingFinished.emit()
    bar = composer.quick_bar
    assert bar.folder_chip.toolTip() == str(deep)
    assert bar.folder_chip.text().startswith('…')
    assert not bar.folder_chip.text().startswith('…/Очень')  # the long name itself is elided
    assert bar.folder_chip.sizeHint().width() <= FOLDER_WIDTH + 60


def test_more_parameters_title(make_window):
    window, _ = make_window()
    assert window.composer.parameters_button.text() == 'Другие параметры'
    assert not window.composer.summary.isVisible()


def test_quick_bar_never_widens_the_window(make_window, qtbot):
    window, _ = make_window()
    bar = window.composer.quick_bar
    bar.setStyleSheet('QPushButton, QLabel { font-size: 17px; }')
    window.resize(window.minimumWidth(), 700)
    QApplication.processEvents()
    qtbot.waitUntil(lambda: window.main_page.horizontalScrollBar().maximum() == 0)
    edge = bar.mapTo(window, QPoint(bar.width(), 0)).x()
    assert edge <= window.width()


def test_narrow_card_moves_chips_to_their_own_line(make_window, qtbot):
    window, _ = make_window()
    composer = window.composer
    bar = composer.quick_bar
    window.resize(1400, 760)
    QApplication.processEvents()
    assert not composer.quick_bar_wrapped
    window.resize(window.minimumWidth(), 760)
    qtbot.waitUntil(lambda: composer.quick_bar_wrapped)
    qtbot.wait(50)  # the moved bar is laid out on the next event-loop turn
    for chip in (bar.kind_chip, bar.quality_chip, bar.folder_chip):
        if chip.isVisible():
            assert chip.width() >= chip.sizeHint().width()  # never squashed into scraps
    assert bar.smart_label.width() >= bar.smart_label.sizeHint().width()
    window.resize(1400, 760)
    qtbot.waitUntil(lambda: not composer.quick_bar_wrapped)


def test_quality_chip_offers_limits_without_a_probe(make_window):
    window, _ = make_window()
    composer = window.composer
    composer.set_service(Service.YOUTUBE)
    bar = composer.quick_bar
    assert composer.url_input.text() == ''
    items = chip_items(bar.quality_chip)
    limit = window.tr.text('quality_limit', height=720)
    assert limit in items
    pick(bar.quality_chip, limit)
    assert window.presenter.settings.presets[Service.YOUTUBE].max_height == 720


def test_default_window_keeps_chips_readable_on_instagram(make_window, qtbot):
    window, _ = make_window()
    window.resize(1180, 760)
    window.nav_buttons[3].click()  # Instagram
    qtbot.wait(50)
    bar = window.composer.quick_bar
    for widget in (bar.kind_chip, bar.quality_chip, bar.folder_chip, bar.smart_label):
        if widget.isVisible():
            assert widget.width() >= widget.sizeHint().width(), widget
