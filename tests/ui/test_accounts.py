from PySide6.QtCore import QTimer

from clipflow.domain.models import Service
from clipflow.infrastructure.auth import NativeAuthGateway
from tests.support.auth import Process, seed
from tests.support.clipboard import context_paste, paste_shortcut


def test_accounts_use_saved_sessions_without_showing_sign_in(make_window, qtbot, tmp_path):
    window, _ = make_window()
    gateway = NativeAuthGateway(tmp_path)
    seed(tmp_path, Service.YOUTUBE, gateway.platform.protect)
    window.presenter.set_auth_gateway(gateway)
    window.accounts_button.click()
    page = window.accounts_page
    assert page.isVisible()
    assert not page.sign_in_buttons[Service.YOUTUBE].isVisible()
    assert page.logout_buttons[Service.YOUTUBE].isVisible()
    assert page.sign_in_buttons[Service.INSTAGRAM].isVisible()
    page.logout_buttons[Service.YOUTUBE].click()
    assert not gateway.status(Service.YOUTUBE).connected
    assert page.sign_in_buttons[Service.YOUTUBE].isVisible()


def test_settings_page_reuses_persistent_theme_and_language(make_window):
    window, _ = make_window()
    window.settings_button.click()
    page = window.settings_page
    page.language_box.setCurrentIndex(page.language_box.findData('en'))
    page.theme_box.setCurrentIndex(page.theme_box.findData('light'))
    assert window.presenter.settings.language == 'en'
    assert window.theme.resolved_mode() == 'light'
    assert page.about_label.text().startswith('ClipFlow')


def test_windows_icon_retained_after_delayed_startup(make_window, qtbot):
    window, _ = make_window()
    window.composer.set_service(Service.INSTAGRAM)
    before = window.windowIcon().cacheKey()
    ticks = []
    QTimer.singleShot(350, lambda: ticks.append(True))
    qtbot.waitUntil(lambda: bool(ticks))
    assert before == window.windowIcon().cacheKey()
    assert not window.windowIcon().isNull()


def test_accounts_getcourse_configuration_is_scoped_and_password_cleared(
    make_window, qtbot, tmp_path
):
    from PySide6.QtWidgets import QPushButton

    from clipflow.ui.accounts import GetCourseDialog

    window, _ = make_window()
    gateway = NativeAuthGateway(tmp_path)
    window.presenter.set_auth_gateway(gateway)
    window.accounts_button.click()
    window.accounts_page.sign_in_buttons[Service.GETCOURSE].click()
    dialog = next(d for d in window._dialogs if isinstance(d, GetCourseDialog))
    dialog.school.setText('https://school.getcourse.ru/pl/teach/control/lesson/view?id=123')
    dialog.email.setText('user@example.test')
    dialog.password.setText('synthetic-private-password')
    button = next(b for b in dialog.findChildren(QPushButton) if b.text() == 'Сохранить')
    button.click()
    assert dialog.password.text() == ''
    assert gateway.status(Service.GETCOURSE).connected
    assert 'user@example.test' in window.accounts_page.status_labels[Service.GETCOURSE].text()
    assert window.presenter.settings.presets[Service.GETCOURSE].auth_profile.startswith('gc-')


def test_auth_preset_sync_retries_after_settings_save_failure(make_window, tmp_path):
    from clipflow.infrastructure.settings import SettingsStore

    window, _ = make_window()
    gateway = NativeAuthGateway(tmp_path)
    seed(tmp_path, Service.YOUTUBE, gateway.platform.protect)

    class Broken:
        def save(self, settings):
            raise OSError('synthetic-private-location')

    window.presenter.settings_store = Broken()
    window.presenter.set_auth_gateway(gateway)
    assert window.presenter.settings.presets[Service.YOUTUBE].auth_profile is None
    window.presenter.settings_store = SettingsStore(tmp_path)
    window.presenter._poll_auth()
    assert window.presenter.settings.presets[Service.YOUTUBE].auth_profile == 'youtube-default'


def test_close_waits_for_auth_child_ack_without_blocking_gui(
    make_window, qtbot, tmp_path, monkeypatch
):
    import clipflow.infrastructure.auth as auth

    process = Process()
    monkeypatch.setattr(auth.subprocess, 'Popen', lambda *a, **k: process)
    window, _ = make_window()
    gateway = NativeAuthGateway(tmp_path)
    window.presenter.set_auth_gateway(gateway)
    window.presenter.sign_in_account(Service.YOUTUBE)
    ticks = []
    window.close()
    assert not window.presenter.is_closed
    QTimer.singleShot(10, lambda: ticks.append(True))
    qtbot.waitUntil(lambda: bool(ticks))
    process.returncode = 0
    qtbot.waitUntil(lambda: window.presenter.is_closed)
    assert gateway.is_closed


def test_getcourse_credentials_support_native_paste(make_window, qtbot, tmp_path, clipboard):
    from clipflow.ui.accounts import GetCourseDialog

    window, _ = make_window()
    window.presenter.set_auth_gateway(NativeAuthGateway(tmp_path))
    window.accounts_button.click()
    window.accounts_page.sign_in_buttons[Service.GETCOURSE].click()
    dialog = next(d for d in window._dialogs if isinstance(d, GetCourseDialog))
    clipboard.setText('user@example.test')
    paste_shortcut(qtbot, dialog.email)
    clipboard.setText('synthetic-private-password')
    context_paste(qtbot, dialog.password)
    assert dialog.email.text() == 'user@example.test'
    assert dialog.password.text() == 'synthetic-private-password'
    dialog.reject()
    assert dialog.password.text() == ''


def test_auth_change_refreshes_probe_without_clearing_link(make_window, tmp_path):
    window, _ = make_window()
    url = 'https://youtu.be/ABC'
    window.url_input.setText(url)
    previous = window.composer._probe_id
    gateway = NativeAuthGateway(tmp_path)
    seed(tmp_path, Service.YOUTUBE, gateway.platform.protect)
    window.presenter.set_auth_gateway(gateway)
    assert window.url_input.text() == url
    assert window.composer._probe_id != previous


class FakeGateway:
    """Signed in to YouTube as profile 'a'; Instagram as 'b'."""

    def __init__(self):
        self.profiles = {Service.YOUTUBE: 'a', Service.INSTAGRAM: 'b'}
        self.logged_out = []
        self.is_closed = False

    def activate_profile(self, service, profile):
        pass

    def poll(self):
        pass

    def status(self, service):
        from clipflow.infrastructure.auth import AuthStatus

        profile = self.profiles.get(service)
        return AuthStatus(service, profile, connected=profile is not None)

    def logout(self, profile):
        self.logged_out.append(profile)
        self.profiles = {s: p for s, p in self.profiles.items() if p != profile}

    def options_for(self, profile, url):
        return {}

    def close(self):
        self.is_closed = True


def test_logout_pauses_only_active_jobs_of_that_profile(make_window, tmp_path):
    from clipflow.domain.models import DownloadOptions, DownloadRequest, Job, JobState
    from clipflow.domain.urls import parse_url

    window, _ = make_window()
    presenter = window.presenter
    paused = []
    presenter.scheduler.pause = paused.append

    def job(identity, profile, state):
        options = DownloadOptions(tmp_path, auth_profile=profile)
        request = DownloadRequest(parse_url('https://youtu.be/' + identity), options)
        return Job(identity, request, state=state)

    for item in (
        job('a1', 'a', JobState.DOWNLOADING),
        job('a2', 'a', JobState.COMPLETED),
        job('b1', 'b', JobState.PROCESSING),
    ):
        presenter.repository.add(item)
    presenter.set_auth_gateway(FakeGateway())
    presenter.logout_account(Service.YOUTUBE)
    assert paused == ['a1']
    assert presenter.auth_gateway.logged_out == ['a']


def test_auth_change_clears_probe_cache(make_window):
    window, _ = make_window()
    presenter = window.presenter
    gateway = FakeGateway()
    presenter.set_auth_gateway(gateway)
    presenter._probe_cache.put(('key',), (720,))
    gateway.profiles.pop(Service.INSTAGRAM)
    presenter._poll_auth()
    assert presenter._probe_cache.get(('key',)) is None
