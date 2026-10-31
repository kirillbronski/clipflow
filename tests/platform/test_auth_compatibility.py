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
from tests.helpers import wait_until
from tests.support.auth import Process, seed


@pytest.fixture(autouse=True)
def auth_root(tmp_path, monkeypatch):
    monkeypatch.setenv('CLIPFLOW_DATA_DIR', str(tmp_path))


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
    assert yt.connected
    assert ig.connected
    assert yt.profile != ig.profile
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
    assert not gateway.status(Service.YOUTUBE).connected
    assert gateway.status(Service.INSTAGRAM).connected
    assert (tmp_path / 'InstagramAuth/session.dat').read_bytes() == other
    assert (tmp_path / 'YouTubeAuth/logout-request').is_file()


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
    assert a is b
    assert len(calls) == 1
    assert '--youtube-login' in calls[0][0][0]
    assert '--language' in calls[0][0][0]
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
    assert handle.process.terminated
    assert gateway.is_closed


def test_no_secret_in_errors_db_or_support_export(tmp_path):
    gateway = NativeAuthGateway(tmp_path)
    folder = tmp_path / 'YouTubeAuth'
    folder.mkdir()
    (folder / 'session.dat').write_bytes(b'bad synthetic-private-token ciphertext')
    status = gateway.status(Service.YOUTUBE)
    assert not status.connected
    assert 'synthetic-private-token' not in repr(status)
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
    assert namespace[0] == 'ClipFlow Tests'
    assert namespace[1].startswith('profile-key-')


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
    assert options['username'] == payload['email']
    assert options['password'] == payload['password']
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
    assert file.is_file()
    assert file.read_bytes() == changed
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
        assert b'synthetic-private-password' not in path.read_bytes()
        assert b'private@example.test' not in path.read_bytes()


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
    assert result.returncode == 2
    assert not outside.exists()


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
    assert result.returncode == 2
    assert original.read_bytes() == b'original-bytes'


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
    assert proof['passed']
    assert proof['rendered']
    assert proof['protected_snapshot']
    assert proof['os']
    assert proof['cpu']


@pytest.mark.native_gui
def test_real_auth_child_single_instance_and_parent_close(tmp_path, monkeypatch):
    if os.environ.get('CLIPFLOW_AUTH_NATIVE') != '1':
        pytest.skip('Run separate native auth job with CLIPFLOW_AUTH_NATIVE=1')
    gateway = NativeAuthGateway(tmp_path)
    handle = gateway.sign_in(Service.YOUTUBE, 'en')
    try:

        def lock_ready():
            assert handle.process.poll() is None
            return (tmp_path / 'YouTubeAuth/window.lock').exists()

        wait_until(lock_ready, timeout=12)
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
        assert second.returncode == 0
        assert 'AUTH already_open' in second.stdout
        assert handle.process.poll() is None
        gateway.close()
        wait_until(lambda: gateway.is_closed, timeout=10)
        assert gateway.is_closed
        assert handle.process.returncode == 0
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
        wait_until(lambda: gateway.is_closed, timeout=12)
        assert gateway.is_closed
        assert handle.process.returncode == 0
        assert not handle._terminated
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


class Stubborn(Process):
    """A sign-in window that ignores the polite close and terminate requests."""

    def terminate(self):
        self.terminated = True


def test_unwritable_close_request_terminates_then_kills_the_window(tmp_path, monkeypatch):
    import clipflow.infrastructure.auth as auth

    monkeypatch.setattr(auth.subprocess, 'Popen', Stubborn)
    gateway = NativeAuthGateway(tmp_path)
    handle = gateway.sign_in(Service.YOUTUBE, 'ru')
    handle.close_path = tmp_path / 'missing-folder/close-request'
    handle.close()
    assert handle.process.terminated
    assert handle.poll().state == 'closing'
    handle._deadline = 0
    assert handle.poll().state == 'signed_out'
    assert handle.process.returncode == -9


def test_closing_a_finished_window_sends_nothing(tmp_path, monkeypatch):
    import clipflow.infrastructure.auth as auth

    monkeypatch.setattr(auth.subprocess, 'Popen', Process)
    handle = NativeAuthGateway(tmp_path).sign_in(Service.YOUTUBE, 'ru')
    handle.process.returncode = 0
    handle.close()
    assert not handle.close_path.exists()
    assert not handle.process.terminated


@pytest.mark.parametrize(
    ('service', 'language', 'closing'),
    [
        (Service.GETCOURSE, 'ru', False),
        (Service.YOUTUBE, 'de', False),
        (Service.YOUTUBE, 'ru', True),
    ],
)
def test_sign_in_is_unavailable_for_other_services_languages_or_after_close(
    tmp_path, service, language, closing
):
    gateway = NativeAuthGateway(tmp_path)
    if closing:
        gateway.close()
    with pytest.raises(MediaFailure, match='auth_unavailable'):
        gateway.sign_in(service, language)


def test_sign_in_window_that_cannot_start_is_reported(tmp_path, monkeypatch):
    import clipflow.infrastructure.auth as auth

    def missing(*args, **kwargs):
        raise FileNotFoundError('python')

    monkeypatch.setattr(auth.subprocess, 'Popen', missing)
    with pytest.raises(MediaFailure, match='auth_launch_failed'):
        NativeAuthGateway(tmp_path).sign_in(Service.INSTAGRAM, 'en')


def test_logout_closes_the_open_sign_in_window(tmp_path, monkeypatch):
    import clipflow.infrastructure.auth as auth

    monkeypatch.setattr(auth.subprocess, 'Popen', Process)
    gateway = NativeAuthGateway(tmp_path)
    handle = gateway.sign_in(Service.YOUTUBE, 'ru')
    gateway.logout('youtube-default')
    assert handle.close_path.is_file()


def test_drain_waits_until_every_window_has_closed(tmp_path, monkeypatch):
    import clipflow.infrastructure.auth as auth

    class SlowToClose(Process):
        polls = 0

        def poll(self):
            self.polls += 1
            if self.polls > 6:
                self.returncode = 0
            return self.returncode

    monkeypatch.setattr(auth.subprocess, 'Popen', SlowToClose)
    gateway = NativeAuthGateway(tmp_path)
    handle = gateway.sign_in(Service.INSTAGRAM, 'ru')
    gateway.drain()
    assert handle.process.returncode == 0
    assert handle.process.polls > 6


def test_no_profile_means_no_credentials(tmp_path):
    assert NativeAuthGateway(tmp_path).options_for(None, 'https://youtu.be/ABC') == {}


def test_school_profile_is_never_given_to_another_site(tmp_path):
    gateway = NativeAuthGateway(tmp_path)
    profile = gateway.configure_getcourse(LESSON, 'email', email='a@b', password='p')
    with pytest.raises(MediaFailure, match='auth_scope_mismatch'):
        gateway.options_for(profile, 'https://youtu.be/ABC')


def test_unexpected_cookie_failure_asks_to_sign_in_without_details(tmp_path, monkeypatch):
    import clipflow.infrastructure.auth as auth

    gateway = NativeAuthGateway(tmp_path)
    seed(tmp_path, Service.YOUTUBE, gateway.platform.protect)

    def broken(cookies):
        raise RuntimeError(cookies[0]['value'])

    monkeypatch.setattr(auth, 'cookie_jar', broken)
    with pytest.raises(MediaFailure) as raised:
        gateway.options_for('youtube-default', 'https://youtu.be/ABC')
    assert raised.value.code == 'auth_required'
    assert 'synthetic-private-token' not in str(raised.value)
    assert raised.value.__suppress_context__


def test_unreadable_school_profile_asks_to_sign_in(tmp_path):
    gateway = NativeAuthGateway(tmp_path)
    profile = gateway.configure_getcourse(LESSON, 'email', email='a@b', password='p')
    (tmp_path / 'GetCourseAuth' / (profile + '.dat')).write_bytes(b'not sealed')
    with pytest.raises(MediaFailure, match='auth_required'):
        gateway.options_for(profile, LESSON)


def test_public_school_downloads_without_credentials(tmp_path):
    gateway = NativeAuthGateway(tmp_path)
    profile = gateway.configure_getcourse(LESSON, 'public')
    assert gateway.status(Service.GETCOURSE).state == 'configured'
    assert gateway.options_for(profile, LESSON) == {}


def test_browser_cookies_are_read_from_the_chosen_browser_and_scoped(tmp_path, monkeypatch):
    from http.cookiejar import Cookie, CookieJar

    import yt_dlp.cookies

    def cookie(domain):
        return Cookie(0, 'sid', 'v-' + domain, None, False, domain, True, True, '/', True,
                      True, None, True, None, None, {}, False)  # fmt: skip

    jar = CookieJar()
    for domain in ('.school.getcourse.ru', '.other.getcourse.ru'):
        jar.set_cookie(cookie(domain))
    sources = []

    def load_cookies(cookie_file, browser, ydl):
        sources.append(browser)
        return jar

    monkeypatch.setattr(yt_dlp.cookies, 'load_cookies', load_cookies)
    gateway = NativeAuthGateway(tmp_path)
    profile = gateway.configure_getcourse(LESSON, 'browser', browser='firefox')
    scoped = gateway.options_for(profile, LESSON)['_cookiejar']
    assert sources == [('firefox',)]
    assert [c.value for c in scoped] == ['v-.school.getcourse.ru']


def test_browser_without_school_cookies_asks_to_sign_in(tmp_path, monkeypatch):
    from http.cookiejar import CookieJar

    import yt_dlp.cookies

    monkeypatch.setattr(yt_dlp.cookies, 'load_cookies', lambda *args: CookieJar())
    gateway = NativeAuthGateway(tmp_path)
    profile = gateway.configure_getcourse(LESSON, 'browser', browser='chrome')
    with pytest.raises(MediaFailure, match='auth_required'):
        gateway.options_for(profile, LESSON)


@pytest.mark.parametrize(
    ('system', 'browser', 'expected'),
    [
        ('darwin', 'yandex', ('chrome', 'Library/Application Support/Yandex/YandexBrowser')),
        ('win32', 'yandex', ('chrome', 'Local/Yandex/YandexBrowser/User Data')),
        ('darwin', 'opera_gx', ('opera', 'Library/Application Support/com.operasoftware.OperaGX')),
        ('win32', 'opera_gx', ('opera', 'Roaming/Opera Software/Opera GX Stable')),
    ],
)
def test_browsers_without_own_reader_use_their_engine_and_profile_folder(
    monkeypatch, tmp_path, system, browser, expected
):
    monkeypatch.setattr(sys, 'platform', system)
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'Local'))
    monkeypatch.setenv('APPDATA', str(tmp_path / 'Roaming'))
    engine, folder = NativeAuthGateway.browser_source(browser)
    assert engine == expected[0]
    assert Path(folder).as_posix().endswith(expected[1])
    assert NativeAuthGateway.browser_source('edge') == ('edge',)


@pytest.mark.parametrize(
    ('method', 'details'),
    [
        ('telepathy', {}),
        ('email', {'email': '  ', 'password': 'p'}),
        ('email', {'email': 'a@b', 'password': ''}),
        ('cookies', {'file': 'no-such-export.txt'}),
        ('browser', {'browser': 'netscape'}),
    ],
)
def test_incomplete_school_settings_are_refused(tmp_path, method, details):
    gateway = NativeAuthGateway(tmp_path)
    with pytest.raises(MediaFailure, match='auth_invalid_settings'):
        gateway.configure_getcourse(LESSON, method, **details)
    assert not (tmp_path / 'GetCourseAuth').exists()


@pytest.mark.parametrize(
    ('content', 'code'),
    [(None, 'auth_required'), ({'method': 'Голубиная почта'}, 'auth_invalid_settings')],
)
def test_unusable_old_school_profile_is_not_imported(tmp_path, content, code):
    gateway = NativeAuthGateway(tmp_path)
    if content is not None:
        sealed = gateway.platform.protect(json.dumps(content).encode())
        (tmp_path / 'getcourse-profile.dat').write_bytes(sealed)
    with pytest.raises(MediaFailure, match=code):
        gateway.import_legacy_getcourse(LESSON)


def browser_cookie(**changes):
    cookie = dict(
        domain='.youtube.com', path='/', name='SAPISID', value='token', expires=-1, secure=True
    )
    return {**cookie, **changes}


@pytest.mark.parametrize(
    'rejected',
    [
        'not a cookie',
        browser_cookie(domain='.evil-youtube.com'),
        browser_cookie(domain=None),
        browser_cookie(value=None),
        browser_cookie(expires=1),
        browser_cookie(expires='never'),
        browser_cookie(path='relative'),
        browser_cookie(name='SAP\0ISID'),
    ],
)
def test_only_well_formed_live_cookies_of_the_service_are_kept(rejected):
    from clipflow.infrastructure.auth_process.sessions import scoped_cookies

    kept = scoped_cookies([rejected, browser_cookie()], 'youtube.com')
    assert [c['value'] for c in kept] == ['token']
    assert scoped_cookies({'not': 'a list'}, 'youtube.com') == []


def test_sign_in_saves_only_a_session_with_its_auth_cookie(tmp_path):
    from clipflow.infrastructure.auth_process.sessions import SessionStore, load_protected

    store = SessionStore(tmp_path / 'YouTubeAuth', Service.YOUTUBE, PlatformServices().protect)
    assert not store.save([browser_cookie(name='PREF')])
    assert not store.snapshot.exists()
    assert store.save([browser_cookie(), browser_cookie(domain='.google.com')])
    written = load_protected(store.snapshot, store.protect)
    assert [c['domain'] for c in written] == ['.youtube.com']


def test_session_saved_after_sign_out_is_dropped(tmp_path):
    from clipflow.infrastructure.auth_process.sessions import SessionStore

    store = SessionStore(tmp_path / 'YouTubeAuth', Service.YOUTUBE, PlatformServices().protect)
    store.logout()
    assert not store.save([browser_cookie()])
    assert not store.snapshot.exists()


def test_oversized_protected_file_is_not_read(tmp_path):
    from clipflow.infrastructure.auth_process.sessions import load_protected

    huge = tmp_path / 'session.dat'
    huge.write_bytes(b'0' * (16 * 1024 * 1024 + 1))

    def protect(data, decrypt=False):
        raise AssertionError('must not decrypt')

    assert load_protected(huge, protect) is None
