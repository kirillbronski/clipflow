from dataclasses import replace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QDialogButtonBox, QLineEdit, QPlainTextEdit

from clipflow.domain.events import SelectionRequired
from clipflow.domain.models import Service
from clipflow.infrastructure.settings import SettingsStore
from clipflow.ui.i18n import CATALOG, Translator
from clipflow.ui.themes import PALETTES, TEXT_PAIRS, ThemeManager
from tests.support.workbench import batch


def contrast(a, b):
    def lum(color):
        c = QColor(color)
        values = [c.redF(), c.greenF(), c.blueF()]
        values = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in values]
        return sum(v * w for v, w in zip(values, (0.2126, 0.7152, 0.0722), strict=True))

    x, y = sorted((lum(a), lum(b)))
    return (y + 0.05) / (x + 0.05)


def test_dark_first_launch_and_persistence(make_window, tmp_path, qtbot):
    window, _ = make_window()
    store = SettingsStore(tmp_path / 'preferences')
    window.presenter.settings_store = store
    assert window.theme.resolved_mode() == 'dark'
    window.theme_actions['light'].trigger()
    assert store.load().theme == 'light' and window.theme.resolved_mode() == 'light'
    window.language_actions['en'].trigger()
    assert store.load().language == 'en' and window.heading.text() == 'All downloads'
    restored, _ = make_window(settings=store.load())
    assert restored.theme.resolved_mode() == 'light' and restored.heading.text() == 'All downloads'


def test_system_palette_change(make_window, qapp):
    window, _ = make_window()
    window.theme_actions['system'].trigger()
    qapp.styleHints().colorSchemeChanged.emit(Qt.ColorScheme.Light)
    assert window.theme.resolved_mode() == 'light'
    qapp.styleHints().colorSchemeChanged.emit(Qt.ColorScheme.Dark)
    assert window.theme.resolved_mode() == 'dark'
    window.theme_actions['light'].trigger()
    qapp.styleHints().colorSchemeChanged.emit(Qt.ColorScheme.Dark)
    assert window.theme.resolved_mode() == 'light'


def test_every_dialog_has_readable_dark_controls(make_window, qtbot):
    window, _ = make_window()
    dialog = batch(window, qtbot)
    dialog.text_input.setPlainText('https://youtu.be/ABC\nbad')
    for widget in (
        dialog,
        dialog.text_input,
        dialog.issues,
        dialog.table,
        dialog.limit_box,
        dialog.accept_button,
    ):
        palette = widget.palette()
        assert (
            contrast(palette.color(QPalette.ColorRole.Text), palette.color(QPalette.ColorRole.Base))
            >= 4.5
        )
        assert (
            contrast(
                palette.color(QPalette.ColorRole.ButtonText),
                palette.color(QPalette.ColorRole.Button),
            )
            >= 4.5
        )
    dialog.reject()
    window._select_dialog(
        'synthetic', SelectionRequired(('one', 'two', 'three'), ('First', 'Second'))
    )
    selection = window._dialogs[-1]
    assert (
        selection.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Cancel).text()
        == 'Отмена'
    )
    selection.reject()
    window._source_dialog('synthetic')
    source = window._dialogs[-1]
    assert source.findChild(QLineEdit).palette().color(QPalette.ColorRole.Base).lightness() < 100
    source.reject()


def test_all_text_pairs_contrast_4_5():
    for mode, tokens in PALETTES.items():
        for foreground, background in TEXT_PAIRS:
            assert contrast(tokens[foreground], tokens[background]) >= 4.5, (
                mode,
                foreground,
                background,
            )


@pytest.mark.parametrize('language', ['ru', 'en'])
def test_ru_en_880px_no_clipping(make_window, qtbot, language):
    window, _ = make_window()
    window.language_actions[language].trigger()
    window.resize(880, 680)
    for service in Service:
        window.composer.set_service(service)
        window.composer.parameters_button.setChecked(True)
        if service == Service.INSTAGRAM:
            window.composer.mode_buttons['profile'].click()
        qtbot.waitUntil(lambda: window.composer_host.horizontalScrollBar().maximum() == 0)
        assert window.url_input.width() >= 180 and window.add_button.width() >= 150
        for button in (window.batch_button, window.add_button, window.start_button):
            icon = 0 if button.icon().isNull() else button.iconSize().width() + 4
            text = button.fontMetrics().horizontalAdvance(button.text())
            assert button.width() >= text + icon + 12
    dialog = batch(window, qtbot)
    assert dialog.accept_button.text() == (
        'Добавить в очередь' if language == 'ru' else 'Add to queue'
    )


def test_service_only_changes_accent_not_global_palette(make_window):
    window, _ = make_window()
    baseline = dict(window.theme.tokens())
    palette = window.palette().color(QPalette.ColorRole.Window)
    icons = []
    for service in Service:
        window.composer.set_service(service)
        assert dict(window.theme.tokens()) == baseline
        assert window.palette().color(QPalette.ColorRole.Window) == palette
        icons.append(window.windowIcon().cacheKey())
    assert len(set(icons)) == 1  # App identity stays stable; service accents remain separate.
    assert not window.windowIcon().isNull()


def test_translation_catalog_and_language_change_preserve_drafts(make_window, qtbot):
    assert set(CATALOG['ru']) == set(CATALOG['en'])
    with pytest.raises(KeyError):
        Translator('en').text('missing.key')
    window, _ = make_window()
    window.url_input.setText('unfinished draft')
    dialog = batch(window, qtbot)
    dialog.text_input.setPlainText('https://youtu.be/ABC\nbad')
    window.language_actions['en'].trigger()
    assert (
        window.url_input.text() == 'unfinished draft'
        and dialog.text_input.toPlainText().endswith('bad')
    )
    assert 'Invalid: 1' in dialog.summary.text()
    assert dialog.model.headerData(1, Qt.Orientation.Horizontal) == 'Material'
    assert 'Неверных' not in dialog.summary.text()


def test_preferences_save_failure_keeps_applied_language_and_theme(make_window):
    window, _ = make_window()

    class Broken:
        def save(self, settings):
            raise OSError('private path')

    window.presenter.settings_store = Broken()
    window.language_actions['en'].trigger()
    window.theme_actions['light'].trigger()
    assert window.presenter.settings.language == 'ru' and window.tr.language == 'ru'
    assert window.theme.resolved_mode() == 'dark' and window.theme_actions['dark'].isChecked()
    assert 'private path' not in window.error_label.text()


def test_closed_window_detaches_application_theme_hook(make_window, qapp):
    window, _ = make_window()
    window.theme_actions['system'].trigger()
    calls = []
    window.theme.changed.connect(lambda: calls.append(True))
    window.close()
    qapp.styleHints().colorSchemeChanged.emit(Qt.ColorScheme.Light)
    qapp.styleHints().colorSchemeChanged.emit(Qt.ColorScheme.Dark)
    assert calls == [], 'A closed workbench must not keep changing the application palette'
