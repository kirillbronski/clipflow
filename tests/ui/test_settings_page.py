"""Settings like 4K: sections on the left, their controls on the right."""

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QLabel, QScrollArea


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


def test_all_sections_present(make_window):
    _, page = open_settings(make_window)
    assert set(page.section_buttons) == {'general', 'accounts', 'about'}


def test_accounts_live_in_settings(make_window):
    window, _ = make_window()
    assert not hasattr(window.sidebar, 'accounts_button')
    window.open_settings('accounts')
    assert window.settings_page.current_section == 'accounts'
    assert window.settings_page.section_title.text() == 'Авторизация'
    assert window.accounts_page.isVisible()


def test_settings_remember_last_section(make_window):
    window, _ = make_window()
    window.open_settings('about')
    window.nav_buttons[0].click()
    assert not window.settings_page.isVisible()
    window.settings_button.click()
    assert window.settings_page.current_section == 'about'
    assert window.heading.text() == 'Настройки'


def test_settings_fit_narrow_window(make_window):
    window, _ = make_window()
    window.resize(window.minimumWidth(), 600)
    window.open_settings('general')
    for area in window.settings_page.findChildren(QScrollArea):
        assert area.horizontalScrollBar().maximum() == 0
        assert area.widget().minimumSizeHint().width() <= area.viewport().width()


def test_preferences_action_opens_settings(make_window):
    window, _ = make_window()
    action = window.preferences_action
    assert action.menuRole() == QAction.MenuRole.PreferencesRole
    assert QKeySequence('Ctrl+,') in action.shortcuts()
    assert action.text() == 'Настройки…'
    window.open_settings('about')
    window.nav_buttons[0].click()
    action.trigger()
    assert window.settings_page.isVisible()
    assert window.settings_page.current_section == 'about'


def test_section_title_is_larger_than_body_text(make_window):
    _, page = open_settings(make_window)
    title = page.section_title.fontInfo().pixelSize()
    assert title >= page.language_box.fontInfo().pixelSize() + 4


def test_texts_point_to_the_sign_in_section():
    from clipflow.ui.i18n import CATALOG

    for language in ('ru', 'en'):
        for key in ('error.auth_required', 'job_error.signin'):
            assert 'Accounts' not in CATALOG[language][key]
            assert 'Аккаунты' not in CATALOG[language][key]
