import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from clipflow.domain.models import Service
from clipflow.infrastructure.auth import NativeAuthGateway
from clipflow.infrastructure.platform import PlatformServices
from clipflow.providers.base import MediaFailure


@pytest.fixture(autouse=True)
def auth_root(tmp_path, monkeypatch):
    monkeypatch.setenv('CLIPFLOW_DATA_DIR', str(tmp_path))


def seed(directory, service, protect):
    folder = directory / ('YouTubeAuth' if service == Service.YOUTUBE else 'InstagramAuth')
    folder.mkdir(parents=True, exist_ok=True)
    cookie = dict(
        domain='.youtube.com' if service == Service.YOUTUBE else '.instagram.com',
        path='/',
        name='SAPISID' if service == Service.YOUTUBE else 'sessionid',
        value='synthetic-private-token',
        expires=-1,
        secure=True,
        httpOnly=True,
    )
    (folder / 'session.dat').write_bytes(protect(json.dumps([cookie]).encode()))
    return folder


def test_old_encrypted_session_readable(tmp_path):
    from tests.fixtures import legacy_profile_codec as old

    gateway = NativeAuthGateway(tmp_path)
    folder = seed(tmp_path, Service.YOUTUBE, old.protect_profile)
    original = (folder / 'session.dat').read_bytes()
    status = gateway.status(Service.YOUTUBE)
    jar = gateway.options_for(status.profile, 'https://youtube.com/watch?v=ABC')['_cookiejar']
    assert next(iter(jar)).value == 'synthetic-private-token'
    assert (folder / 'session.dat').read_bytes() == original
    encoded = PlatformServices(tmp_path).protect(b'roundtrip')
    assert old.protect_profile(encoded, decrypt=True) == b'roundtrip'


def test_youtube_instagram_isolation(tmp_path):
    gateway = NativeAuthGateway(tmp_path)
    for service in (Service.YOUTUBE, Service.INSTAGRAM):
        seed(tmp_path, service, gateway.platform.protect)
    yt = gateway.status(Service.YOUTUBE)
    ig = gateway.status(Service.INSTAGRAM)
    assert yt.connected and ig.connected and yt.profile != ig.profile
    with pytest.raises(MediaFailure, match='auth_scope_mismatch'):
        gateway.options_for(yt.profile, 'https://instagram.com/p/ABC/')
    with pytest.raises(MediaFailure, match='auth_scope_mismatch'):
        gateway.options_for(ig.profile, 'https://youtu.be/ABC')


def test_logout_only_selected_service(tmp_path):
    gateway = NativeAuthGateway(tmp_path)
    for service in (Service.YOUTUBE, Service.INSTAGRAM):
        seed(tmp_path, service, gateway.platform.protect)
    other = (tmp_path / 'InstagramAuth/session.dat').read_bytes()
    gateway.logout(gateway.status(Service.YOUTUBE).profile)
    assert (
        not gateway.status(Service.YOUTUBE).connected
        and gateway.status(Service.INSTAGRAM).connected
    )
    assert (tmp_path / 'InstagramAuth/session.dat').read_bytes() == other
    assert (tmp_path / 'YouTubeAuth/logout-request').is_file()


class Process:
    def __init__(self, *args, **kwargs):
        self.returncode = None
        self.terminated = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    def kill(self):
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


def test_auth_process_single_instance(tmp_path, monkeypatch):
    import clipflow.infrastructure.auth as auth

    calls = []

    def launch(*args, **kwargs):
        calls.append((args, kwargs))
        return Process()

    monkeypatch.setattr(auth.subprocess, 'Popen', launch)
    gateway = NativeAuthGateway(tmp_path)
    a = gateway.sign_in(Service.YOUTUBE, 'en')
    b = gateway.sign_in(Service.YOUTUBE, 'ru')
    assert a is b and len(calls) == 1
    assert '--youtube-login' in calls[0][0][0] and '--language' in calls[0][0][0]
    assert 'synthetic-private-token' not in repr(calls)
    gateway.close()
    a.process.returncode = 0
    assert gateway.is_closed


def test_close_parent_handles_child(tmp_path, monkeypatch):
    import clipflow.infrastructure.auth as auth

    monkeypatch.setattr(auth.subprocess, 'Popen', lambda *a, **k: Process())
    gateway = NativeAuthGateway(tmp_path)
    handle = gateway.sign_in(Service.INSTAGRAM, 'ru')
    gateway.close()
    assert handle.close_path.is_file()
    handle._deadline = 0
    handle.poll()
    assert handle.process.terminated and gateway.is_closed


def test_no_secret_in_errors_db_or_support_export(tmp_path):
    gateway = NativeAuthGateway(tmp_path)
    folder = tmp_path / 'YouTubeAuth'
    folder.mkdir()
    (folder / 'session.dat').write_bytes(b'bad synthetic-private-token ciphertext')
    status = gateway.status(Service.YOUTUBE)
    assert not status.connected and 'synthetic-private-token' not in repr(status)
    with pytest.raises(MediaFailure) as failure:
        gateway.options_for('youtube-default', 'https://youtu.be/ABC')
    assert str(failure.value) == 'auth_required'
    assert 'synthetic-private-token' not in json.dumps(gateway.support_status())


def test_macos_data_and_keychain_namespace_unchanged(tmp_path, monkeypatch):
    import clipflow.infrastructure.platform as platform

    monkeypatch.setattr(platform, 'SYSTEM', 'darwin')
    monkeypatch.delenv('CLIPFLOW_DATA_DIR')
    assert platform.data_directory() == Path.home() / 'Library/Application Support/ClipFlow'
    assert PlatformServices(tmp_path).key_namespace() == ('ClipFlow', 'profile-encryption-key-v1')
    monkeypatch.setenv('CLIPFLOW_DATA_DIR', str(tmp_path))
    namespace = PlatformServices(tmp_path).key_namespace()
    assert namespace[0] == 'ClipFlow Tests' and namespace[1].startswith('profile-key-')


def test_getcourse_legacy_requires_explicit_school_binding(tmp_path):
    gateway = NativeAuthGateway(tmp_path)
    source = tmp_path / 'getcourse-profile.dat'
    payload = {
        'method': 'Email и пароль',
        'email': 'user@example.test',
        'password': 'synthetic-private-password',
        'file': '',
    }
    original = gateway.platform.protect(json.dumps(payload).encode())
    source.write_bytes(original)
    assert not gateway.status(Service.GETCOURSE).connected
    ref = gateway.import_legacy_getcourse(
        'https://school.getcourse.ru/pl/teach/control/lesson/view?id=123'
    )
    options = gateway.options_for(
        ref, 'https://school.getcourse.ru/pl/teach/control/lesson/view?id=124'
    )
    assert options['username'] == payload['email'] and options['password'] == payload['password']
    with pytest.raises(MediaFailure, match='auth_scope_mismatch'):
        gateway.options_for(ref, 'https://other.getcourse.ru/pl/teach/control/lesson/view?id=123')
    assert source.read_bytes() == original
    assert payload['password'] not in repr(gateway.status(Service.GETCOURSE))


def test_scoped_logout_preserves_legacy_profile_updated_during_import(tmp_path, monkeypatch):
    gateway = NativeAuthGateway(tmp_path)
    file = tmp_path / 'getcourse-profile.dat'
    payload = {
        'method': 'Email и пароль',
        'email': 'user@example.test',
        'password': 'synthetic-old-password',
        'file': '',
    }
    file.write_bytes(gateway.platform.protect(json.dumps(payload).encode()))
    changed = gateway.platform.protect(
        json.dumps(
            dict(payload, email='other@example.test', password='synthetic-new-password')
        ).encode()
    )
    original = gateway.configure_getcourse

    def concurrent_update(*args, **kwargs):
        file.write_bytes(changed)
        return original(*args, **kwargs)

    monkeypatch.setattr(gateway, 'configure_getcourse', concurrent_update)
    profile = gateway.import_legacy_getcourse(
        'https://school.getcourse.ru/pl/teach/control/lesson/view?id=123'
    )
    gateway.logout(profile)
    assert file.is_file() and file.read_bytes() == changed
    assert not gateway.status(Service.GETCOURSE).connected


def test_unknown_getcourse_reference_is_not_a_startup_crash(tmp_path):
    gateway = NativeAuthGateway(tmp_path)
    gateway.activate_profile(Service.GETCOURSE, 'old-unknown-profile')
    assert not gateway.status(Service.GETCOURSE).connected


def test_getcourse_export_is_filtered_to_selected_school(tmp_path):
    gateway = NativeAuthGateway(tmp_path)
    file = tmp_path / 'export.txt'
    file.write_text(
        '# Netscape HTTP Cookie File\n'
        '.school.getcourse.ru\tTRUE\t/\tTRUE\t2147483647\tsid\tsynthetic-school\n'
        '.other.getcourse.ru\tTRUE\t/\tTRUE\t2147483647\tsid\tother-school\n'
        '.google.com\tTRUE\t/\tTRUE\t2147483647\tSID\tunrelated\n',
        encoding='utf-8',
    )
    original = file.read_bytes()
    url = 'https://school.getcourse.ru/pl/teach/control/lesson/view?id=123'
    ref = gateway.configure_getcourse(url, 'cookies', file=str(file))
    jar = gateway.options_for(ref, url)['_cookiejar']
    assert [(c.domain, c.value) for c in jar] == [('.school.getcourse.ru', 'synthetic-school')]
    assert file.read_bytes() == original


def test_direct_getcourse_player_never_receives_school_credentials(tmp_path):
    gateway = NativeAuthGateway(tmp_path)
    profile = gateway.configure_getcourse(
        'https://school.getcourse.ru/pl/teach/control/lesson/view?id=123',
        'email',
        email='user@example.test',
        password='synthetic-private-password',
    )
    player = 'https://player02.getcourse.ru/sign-player/?json=eyJ2aWRlb19oYXNoIjoiZmlyc3QifQ=='
    assert gateway.options_for(profile, player) == {}
    with pytest.raises(MediaFailure, match='auth_invalid_school'):
        gateway.configure_getcourse(
            player, 'email', email='user@example.test', password='synthetic-private-password'
        )


def test_credentials_only_referenced_in_queue_and_settings(tmp_path):
    from dataclasses import replace

    from clipflow.application.submission import SubmissionService
    from clipflow.infrastructure.repository import SqliteJobRepository
    from clipflow.infrastructure.settings import AppSettings, SettingsStore

    gateway = NativeAuthGateway(tmp_path)
    url = 'https://school.getcourse.ru/pl/teach/control/lesson/view?id=123'
    ref = gateway.configure_getcourse(
        url, 'email', email='private@example.test', password='synthetic-private-password'
    )
    settings = AppSettings()
    presets = dict(settings.presets)
    presets[Service.GETCOURSE] = replace(presets[Service.GETCOURSE], auth_profile=ref)
    store = SettingsStore(tmp_path)
    store.save(replace(settings, presets=presets))
    repo = SqliteJobRepository(tmp_path / 'queue.sqlite3')
    submission = SubmissionService(repo)
    submission.submit(submission.preview(url, presets))
    repo.close()
    for path in (store.path, tmp_path / 'queue.sqlite3'):
        assert (
            b'synthetic-private-password' not in path.read_bytes()
            and b'private@example.test' not in path.read_bytes()
        )


def test_gateway_import_does_not_load_webengine_or_tk(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            '-c',
            'import sys; import clipflow.infrastructure.auth; '
            'assert "tkinter" not in sys.modules; '
            'assert "PySide6.QtWebEngineWidgets" not in sys.modules',
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0


def test_bootstrap_dispatches_auth_before_main_window(monkeypatch):
    import clipflow.infrastructure.auth_process.__main__ as auth
    import clipflow.ui.bootstrap as bootstrap

    seen = []

    def forbidden(*args, **kwargs):
        raise AssertionError('Downloader must not be created for an auth flag')

    monkeypatch.setattr(bootstrap, 'create_application', forbidden)
    monkeypatch.setattr(auth, 'main', lambda arguments: seen.append(arguments) or 17)
    assert bootstrap.main(['ClipFlow', '--youtube-login', '--language', 'en']) == 17
    assert seen == [['--youtube-login', '--language', 'en']]


def test_auth_self_test_cannot_write_outside_isolated_root(tmp_path):
    outside = tmp_path.parent / (tmp_path.name + '-outside')
    result = subprocess.run(
        [sys.executable, 'run.py', '--auth-self-test', str(outside), '--data-dir', str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=40,
    )
    assert result.returncode == 2 and not outside.exists()


def test_auth_self_test_refuses_existing_profile_contents(tmp_path):
    directory = tmp_path / 'existing'
    directory.mkdir()
    original = directory / 'preserve.dat'
    original.write_bytes(b'original-bytes')
    result = subprocess.run(
        [sys.executable, 'run.py', '--auth-self-test', str(directory), '--data-dir', str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=40,
    )
    assert result.returncode == 2 and original.read_bytes() == b'original-bytes'


@pytest.mark.parametrize('flag', ['--auth-self-test', '--instagram-auth-self-test'])
@pytest.mark.native_gui
def test_auth_self_tests_native(tmp_path, flag):
    if os.environ.get('CLIPFLOW_AUTH_NATIVE') != '1':
        pytest.skip('Run separate native auth job with CLIPFLOW_AUTH_NATIVE=1')
    assert os.environ.get('QT_QPA_PLATFORM') in {'windows', 'cocoa'}
    from clipflow.infrastructure.settings import AppSettings, SettingsStore

    SettingsStore(tmp_path).save(AppSettings(theme='light'))
    destination = tmp_path / ('instagram' if 'instagram' in flag else 'youtube')
    report = tmp_path / 'auth-proof.json'
    result = subprocess.run(
        [
            sys.executable,
            'run.py',
            flag,
            str(destination),
            '--data-dir',
            str(tmp_path),
            '--report',
            str(report),
        ],
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'PASS isolated WebEngine render' in result.stdout
    assert 'theme=light' in result.stdout
    assert not (destination / 'session.dat').exists()
    import json

    proof = json.loads(report.read_text(encoding='utf-8'))
    assert (
        proof['passed']
        and proof['rendered']
        and proof['protected_snapshot']
        and proof['os']
        and proof['cpu']
    )


@pytest.mark.native_gui
def test_real_auth_child_single_instance_and_parent_close(tmp_path, monkeypatch):
    if os.environ.get('CLIPFLOW_AUTH_NATIVE') != '1':
        pytest.skip('Run separate native auth job with CLIPFLOW_AUTH_NATIVE=1')
    gateway = NativeAuthGateway(tmp_path)
    handle = gateway.sign_in(Service.YOUTUBE, 'en')
    try:
        deadline = time.monotonic() + 12
        while not (tmp_path / 'YouTubeAuth/window.lock').exists() and time.monotonic() < deadline:
            assert handle.process.poll() is None
            time.sleep(0.025)
        assert (tmp_path / 'YouTubeAuth/window.lock').exists()
        second = subprocess.run(
            [
                sys.executable,
                '-m',
                'clipflow.infrastructure.auth_process',
                '--youtube-login',
                '--data-dir',
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert second.returncode == 0 and 'AUTH already_open' in second.stdout
        assert handle.process.poll() is None
        gateway.close()
        deadline = time.monotonic() + 10
        while not gateway.is_closed and time.monotonic() < deadline:
            time.sleep(0.025)
        assert gateway.is_closed and handle.process.returncode == 0
    finally:
        gateway.drain()


@pytest.mark.native_gui
def test_parent_close_during_auth_startup_is_not_lost(tmp_path, monkeypatch):
    if os.environ.get('CLIPFLOW_AUTH_NATIVE') != '1':
        pytest.skip('Run separate native auth job with CLIPFLOW_AUTH_NATIVE=1')
    import clipflow.infrastructure.auth as auth

    original = subprocess.Popen

    def delayed(arguments, **kwargs):
        command = [
            arguments[0],
            '-c',
            'import time; time.sleep(.4); '
            'from clipflow.infrastructure.auth_process.__main__ import main; '
            'raise SystemExit(main())',
            *arguments[3:],
        ]
        return original(command, **kwargs)

    monkeypatch.setattr(auth.subprocess, 'Popen', delayed)
    gateway = NativeAuthGateway(tmp_path)
    handle = gateway.sign_in(Service.YOUTUBE, 'en')
    try:
        gateway.close()
        handle._deadline = time.monotonic() + 8
        deadline = time.monotonic() + 12
        while not gateway.is_closed and time.monotonic() < deadline:
            time.sleep(0.025)
        assert gateway.is_closed and handle.process.returncode == 0 and not handle._terminated
    finally:
        gateway.drain()


LESSON = 'https://school.getcourse.ru/pl/teach/control/lesson/view?id=123'


@pytest.mark.parametrize('failure', [OSError('auth_protection_failed'), ValueError('bad json')])
def test_getcourse_storage_failure_is_reported_as_storage(tmp_path, monkeypatch, failure):
    gateway = NativeAuthGateway(tmp_path)

    def broken(data, decrypt=False):
        raise failure

    monkeypatch.setattr(gateway.platform, 'protect', broken)
    with pytest.raises(MediaFailure) as raised:
        gateway.configure_getcourse(LESSON, 'email', email='a@b', password='p')
    assert raised.value.code == 'auth_storage_failed'


def test_getcourse_storage_bug_is_not_disguised_as_storage(tmp_path, monkeypatch):
    gateway = NativeAuthGateway(tmp_path)

    def buggy(data, decrypt=False):
        raise RuntimeError('programming error')

    monkeypatch.setattr(gateway.platform, 'protect', buggy)
    with pytest.raises(RuntimeError):
        gateway.configure_getcourse(LESSON, 'email', email='a@b', password='p')
