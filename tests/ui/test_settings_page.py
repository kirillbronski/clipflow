"""Settings like 4K: sections on the left, their controls on the right."""

from PySide6.QtWidgets import QLabel


def open_settings(make_window):
    window, _ = make_window()
    window.settings_button.click()
    return window, window.settings_page


def test_sections_switch_pages(make_window):
    _, page = open_settings(make_window)
    assert page.current_section == 'general'
    assert page.section_title.text() == 'Основные'
    page.section_buttons['about'].click()
    assert page.current_section == 'about'
    assert page.section_title.text() == 'О программе'
    assert page.about_label.isVisible()
    assert not page.language_box.isVisible()


def test_auto_start_toggle_and_composer_stay_in_sync(make_window):
    window, page = open_settings(make_window)
    page.auto_start_toggle.click()
    assert window.presenter.settings.auto_start
    assert window.composer.auto_start.isChecked()
    window.composer.auto_start.click()
    assert not window.presenter.settings.auto_start
    assert not page.auto_start_toggle.isChecked()


def test_auto_start_toggle_reverts_when_save_fails(make_window, monkeypatch):
    window, page = open_settings(make_window)
    monkeypatch.setattr(window.presenter, 'set_auto_start', lambda enabled: False)
    page.auto_start_toggle.click()
    assert not page.auto_start_toggle.isChecked()


def test_settings_follow_language_switch(make_window):
    _, page = open_settings(make_window)
    page.language_box.setCurrentIndex(page.language_box.findData('en'))
    assert page.section_buttons['general'].text().endswith('General')
    assert page.section_title.text() == 'General'
    texts = {label.text() for label in page.findChildren(QLabel)}
    assert 'Start downloading as soon as added' in texts
    assert any(text.startswith('Downloads begin as soon as') for text in texts)


def test_hidden_sections_are_absent(make_window):
    _, page = open_settings(make_window)
    assert set(page.section_buttons) == {'general', 'about'}
