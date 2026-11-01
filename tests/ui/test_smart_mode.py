"""Smart mode: a paste goes straight into the queue and starts downloading."""

import pytest
from PySide6.QtCore import Qt

from clipflow.domain.models import ContentKind, Service
from tests.support.clipboard import paste_shortcut

VIDEO = 'https://youtu.be/smartA'


def smart_window(make_window):
    window, provider = make_window()
    window.composer.quick_bar.smart_toggle.click()
    assert window.presenter.settings.smart_mode is True
    return window, provider


def jobs(window):
    return list(window.presenter.repository.list())


@pytest.mark.parametrize('route', ['shortcut', 'button', 'menu'])
def test_smart_paste_by_shortcut_button_and_menu(make_window, qtbot, clipboard, route):
    window, provider = smart_window(make_window)
    clipboard.setText(VIDEO)
    if route == 'shortcut':
        paste_shortcut(qtbot, window.composer.url_input)
    elif route == 'button':
        window.composer.paste_button.click()
    else:
        window.composer.url_input.paste()
    assert [j.request.link.canonical_id for j in jobs(window)] == ['smartA']
    assert window.composer.url_input.text() == ''
    assert window.smart_message.text() == 'Добавлено: 1'
    qtbot.waitUntil(provider.started.is_set, timeout=3000)


def test_smart_paste_mixed_text(make_window, clipboard):
    window, _ = smart_window(make_window)
    clipboard.setText(
        f'{VIDEO}\nhttps://www.youtube.com/playlist?list=PLsmart\nне ссылка\n'
        'https://www.instagram.com/p/SMART/'
    )
    window.composer.url_input.paste()
    kinds = sorted((j.request.link.service, j.request.link.kind) for j in jobs(window))
    assert kinds == sorted(
        [
            (Service.YOUTUBE, ContentKind.VIDEO),
            (Service.YOUTUBE, ContentKind.PLAYLIST),
            (Service.INSTAGRAM, ContentKind.POST),
        ]
    )
    assert window.composer.url_input.text() == 'не ссылка'
    assert window.error_label.isVisible()


def test_smart_paste_duplicate(make_window, clipboard):
    window, _ = smart_window(make_window)
    clipboard.setText(VIDEO)
    window.composer.url_input.paste()
    window.composer.url_input.paste()
    assert len(jobs(window)) == 1
    assert window.smart_message.text() == 'Добавлено: 0, уже в очереди: 1'


def test_smart_paste_other_service_uses_its_settings(make_window, clipboard):
    window, _ = smart_window(make_window)
    window.composer.set_service(Service.YOUTUBE)
    clipboard.setText('https://www.instagram.com/p/SMART/')
    window.composer.url_input.paste()
    (job,) = jobs(window)
    assert job.request.options == window.presenter.settings.presets[Service.INSTAGRAM]


def test_smart_off_pastes_plainly(make_window, clipboard):
    window, _ = smart_window(make_window)
    window.composer.quick_bar.smart_toggle.click()
    assert window.presenter.settings.smart_mode is False
    clipboard.setText(VIDEO)
    window.composer.url_input.paste()
    assert window.composer.url_input.text() == VIDEO
    assert jobs(window) == []


def test_typing_and_enter_are_not_smart(make_window, qtbot):
    window, _ = smart_window(make_window)
    field = window.composer.url_input
    field.setText(VIDEO)
    assert jobs(window) == []
    qtbot.keyClick(field, Qt.Key.Key_Return)
    assert len(jobs(window)) == 1


def test_smart_toggles_stay_in_sync(make_window):
    window, _ = make_window()
    toggle = window.composer.quick_bar.smart_toggle
    page_toggle = window.settings_page.smart_mode_toggle
    toggle.click()
    assert page_toggle.isChecked()
    page_toggle.click()
    assert not toggle.isChecked()
    assert window.presenter.settings.smart_mode is False


def test_smart_message_disappears(make_window, qtbot, clipboard, monkeypatch):
    import clipflow.ui.window as window_module

    monkeypatch.setattr(window_module, 'SMART_MESSAGE_MS', 50)
    window, _ = smart_window(make_window)
    clipboard.setText(VIDEO)
    window.composer.url_input.paste()
    assert window.smart_message.isVisible()
    qtbot.waitUntil(lambda: not window.smart_message.isVisible(), timeout=2000)
