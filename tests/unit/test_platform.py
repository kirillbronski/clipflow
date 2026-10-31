"""Native services: where data lives, how sessions are sealed, how folders open."""

import sys
import types
from pathlib import Path

import pytest
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog

from clipflow.infrastructure import platform
from clipflow.infrastructure.platform import PlatformServices


class Keychain:
    """The macOS Keychain as the keyring backend sees it: one secret per service and account."""

    secrets: dict
    writes: list

    def __init__(self, fail=None):
        self.fail = fail

    def get_password(self, service, account):
        if self.fail:
            raise self.fail
        return self.secrets.get((service, account))

    def set_password(self, service, account, value):
        self.writes.append((service, account))
        self.secrets[(service, account)] = value


@pytest.fixture
def keychain(monkeypatch):
    Keychain.secrets, Keychain.writes = {}, []
    monkeypatch.setattr(platform, 'SYSTEM', 'darwin')
    backend = types.SimpleNamespace(Keyring=Keychain)
    monkeypatch.setitem(sys.modules, 'keyring.backends.macOS', backend)
    return backend


@pytest.fixture
def services(tmp_path, monkeypatch):
    monkeypatch.setenv('CLIPFLOW_DATA_DIR', str(tmp_path))
    return PlatformServices(tmp_path)


def test_data_lives_in_the_system_folder_of_each_os(monkeypatch, tmp_path):
    monkeypatch.delenv('CLIPFLOW_DATA_DIR', raising=False)
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    monkeypatch.setattr(platform, 'SYSTEM', 'win32')
    assert platform.data_directory() == tmp_path / 'ClipFlow'
    monkeypatch.setattr(platform, 'SYSTEM', 'darwin')
    assert platform.data_directory() == Path.home() / 'Library/Application Support/ClipFlow'


def test_key_is_created_once_and_reused(keychain, services):
    sealed = services.protect(b'cookies')
    again = services.protect(b'more')
    assert len(Keychain.writes) == 1
    assert services.protect(sealed, decrypt=True) == b'cookies'
    assert services.protect(again, decrypt=True) == b'more'


def test_opening_a_session_without_a_key_fails_safely(keychain, services):
    with pytest.raises(OSError, match='auth_protection_failed'):
        services.protect(b'sealed elsewhere', decrypt=True)
    assert Keychain.writes == []


def test_keychain_failure_reveals_no_details(monkeypatch, keychain, services):
    keychain.Keyring = lambda: Keychain(fail=RuntimeError('secret-key-material'))
    with pytest.raises(OSError, match='auth_protection_failed') as raised:
        services.protect(b'cookies')
    assert 'secret-key-material' not in str(raised.value)
    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__


def test_windows_seals_sessions_with_dpapi(monkeypatch, services):
    calls = []

    def dpapi(data, decrypt=False):
        calls.append(decrypt)
        if decrypt:
            raise OSError('The data is invalid')
        return b'dpapi:' + data

    monkeypatch.setattr(platform, 'SYSTEM', 'win32')
    monkeypatch.setattr(platform, '_protect_windows', dpapi)
    assert services.protect(b'cookies') == b'dpapi:cookies'
    with pytest.raises(OSError, match='auth_protection_failed'):
        services.protect(b'broken', decrypt=True)
    assert calls == [False, True]


def test_other_systems_refuse_to_store_sessions(monkeypatch, services):
    monkeypatch.setattr(platform, 'SYSTEM', 'linux')
    with pytest.raises(OSError, match='auth_protection_failed'):
        services.protect(b'cookies')


class Desktop:
    """The system file manager: records the folders it was asked to open."""

    def __init__(self):
        self.folders = []
        self.works = True

    def open_url(self, url):
        self.folders.append(Path(url.toLocalFile()))
        return self.works


@pytest.fixture
def desktop(monkeypatch):
    desktop = Desktop()
    monkeypatch.setattr(QDesktopServices, 'openUrl', staticmethod(desktop.open_url))
    return desktop


def test_reveal_opens_the_folder_of_a_file(desktop, services, tmp_path):
    song = tmp_path / 'song.mp3'
    song.write_bytes(b'')
    services.reveal(song)
    services.reveal(tmp_path)
    assert desktop.folders == [tmp_path.resolve(), tmp_path.resolve()]


def test_reveal_reports_a_missing_or_unopenable_folder(desktop, services, tmp_path):
    with pytest.raises(OSError, match='folder_missing'):
        services.reveal(tmp_path / 'gone/song.mp3')
    assert desktop.folders == []
    desktop.works = False
    with pytest.raises(OSError, match='folder_missing'):
        services.reveal(tmp_path)


def test_choose_folder_returns_the_choice_or_nothing(monkeypatch, services, tmp_path):
    answers = [str(tmp_path), '']
    seen = []

    def dialog(parent, title, initial):
        seen.append(initial)
        return answers.pop(0)

    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', staticmethod(dialog))
    assert services.choose_folder(None, tmp_path) == tmp_path.resolve()
    assert services.choose_folder(None, tmp_path) is None
    assert seen == [str(tmp_path), str(tmp_path)]
