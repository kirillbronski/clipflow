"""Startup: bundled tools, the installer's language, a reset warning and a clean exit."""

import sys
import time

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

import clipflow.ui.bootstrap as bootstrap
from clipflow.version import APP_VERSION


@pytest.fixture
def frozen(monkeypatch, tmp_path):
    """A packaged build: the executable and its installer marker live in tmp_path/app."""
    folder = tmp_path / 'app'
    folder.mkdir()
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', str(folder / 'ClipFlow.exe'))
    return folder


def close(window, qtbot):
    window.presenter.shutdown()
    qtbot.waitUntil(lambda: window.presenter.is_closed)
    window.dispose_ui()


def test_tools_bundled_with_the_build_win_over_the_system_ones(monkeypatch, tmp_path):
    suffix = '.exe' if sys.platform == 'win32' else ''
    name = 'ffmpeg' + suffix
    (tmp_path / 'bin').mkdir()
    (tmp_path / 'bin' / name).write_bytes(b'')
    monkeypatch.setattr(sys, '_MEIPASS', str(tmp_path), raising=False)
    monkeypatch.setattr(bootstrap.shutil, 'which', lambda name: '/usr/bin/' + name)
    assert bootstrap._binary('ffmpeg') == str(tmp_path / 'bin' / name)
    assert bootstrap._binary('no-such-tool') == '/usr/bin/no-such-tool' + suffix


def test_unreadable_installer_language_is_ignored(frozen, tmp_path):
    (frozen / 'language.txt').write_bytes(b'\xff\xfe\xfa broken')
    assert bootstrap.installer_language(tmp_path / 'profile') is None
    (frozen / 'language.txt').unlink()
    (frozen / 'language.txt').mkdir()
    assert bootstrap.installer_language(tmp_path / 'profile') is None


def test_installer_language_is_saved_on_first_start(frozen, tmp_path, qtbot):
    from clipflow.infrastructure.settings import SettingsStore

    (frozen / 'language.txt').write_text(APP_VERSION + ':en', encoding='utf-8')
    profile = tmp_path / 'profile'
    _, window = bootstrap.create_application(['clipflow-test'], data_dir=profile)
    try:
        assert window.presenter.settings.language == 'en'
        assert SettingsStore(profile).load().language == 'en'
    finally:
        close(window, qtbot)


def test_reset_settings_are_reported_in_the_window(monkeypatch, tmp_path, qtbot):
    from clipflow.ui.window import MainWindow

    shown = []
    monkeypatch.setattr(MainWindow, '_show_error', lambda self, code: shown.append(code))
    profile = tmp_path / 'profile'
    profile.mkdir()
    (profile / 'settings-v2.json').write_text('{not json', encoding='utf-8')
    _, window = bootstrap.create_application(['clipflow-test'], data_dir=profile)
    try:
        assert shown == ['settings_reset']
    finally:
        close(window, qtbot)


def test_failed_start_releases_the_queue_database(monkeypatch, tmp_path):
    closed = []

    class Repository(bootstrap.SqliteJobRepository):
        def close(self):
            closed.append(True)
            super().close()

    def broken(directory):
        raise RuntimeError('auth store unavailable')

    monkeypatch.setattr(bootstrap, 'SqliteJobRepository', Repository)
    monkeypatch.setattr(bootstrap, 'NativeAuthGateway', broken)
    with pytest.raises(RuntimeError, match='auth store unavailable'):
        bootstrap.create_application(['clipflow-test'], data_dir=tmp_path)
    assert closed == [True]


class SignInWindow:
    """A sign-in process that needs a moment to exit after it is asked to close."""

    def __init__(self, args, **kwargs):
        self.close_request = None
        self.asked_at = None
        self.returncode = None

    def poll(self):
        if self.asked_at is None and self.close_request and self.close_request.exists():
            self.asked_at = time.monotonic()
        if self.asked_at is not None and time.monotonic() - self.asked_at > 0.2:
            self.returncode = 0
        return self.returncode


def test_normal_run_waits_for_running_work_before_exit(monkeypatch, tmp_path, qtbot):
    import clipflow.infrastructure.auth as auth
    from clipflow.domain.models import Job, Service
    from tests.support.scheduler import request

    def planned_title(provider, request, context):
        while not context.cancel.wait(0.005):
            pass
        context.cancel.raise_if_cancelled()

    created = []
    real = bootstrap.create_application

    def create(argv):
        app, window = real(argv, data_dir=tmp_path)
        created.append(window)
        return app, window

    def run(app):
        presenter = created[0].presenter
        assert created[0].isVisible()
        assert presenter.executor.request_title(Job('job-1', request()), lambda *args: None)
        handle = presenter.auth_gateway.sign_in(Service.YOUTUBE, 'ru')
        handle.process.close_request = handle.close_path
        created.append(handle.process)
        return 7

    monkeypatch.setattr(bootstrap.YouTubeProvider, 'planned_title', planned_title)
    monkeypatch.setattr(auth.subprocess, 'Popen', SignInWindow)
    monkeypatch.setattr(bootstrap, 'create_application', create)
    monkeypatch.setattr(QApplication, 'exec', run)
    monkeypatch.setattr(QMessageBox, 'critical', lambda *args: pytest.fail('no error expected'))
    assert bootstrap.main(['clipflow-test']) == 7
    window, sign_in = created
    assert window.presenter.executor.is_closed
    assert not window.presenter.executor.naming
    assert sign_in.returncode == 0
    assert window.presenter.is_closed
