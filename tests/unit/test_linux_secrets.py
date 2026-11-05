"""Linux secret-store availability and safe, temporary sign-in encryption."""

import pytest
from cryptography.fernet import Fernet
from keyring.errors import KeyringLocked

from clipflow.infrastructure import linux_secrets, platform
from clipflow.infrastructure.auth_process.sessions import atomic_protected, load_protected


class Backend:
    def __init__(self, error=None):
        self.value = None
        self.error = error

    def get_password(self, service, account):
        if self.error:
            raise self.error
        return self.value

    def set_password(self, service, account, value):
        self.value = value


def test_creates_and_returns_key_when_missing():
    backend = Backend()
    key = linux_secrets.fernet_key('test', 'account', create=True, backend=backend)
    assert Fernet(key).decrypt(Fernet(key).encrypt(b'cookie')) == b'cookie'
    assert linux_secrets.fernet_key('test', 'account', create=True, backend=backend) == key
    assert backend.value == key


def test_returns_none_without_create():
    backend = Backend()
    assert linux_secrets.fernet_key('test', 'account', create=False, backend=backend) is None
    assert backend.value is None


@pytest.mark.parametrize('error', [KeyringLocked('private'), OSError('private')])
def test_locked_or_missing_store_is_unavailable(error):
    with pytest.raises(
        linux_secrets.SecretStoreUnavailable, match='^auth_secret_store_unavailable$'
    ) as raised:
        linux_secrets.fernet_key('test', 'account', create=True, backend=Backend(error))
    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__


def test_dismissed_unlock_is_unavailable():
    exceptions = pytest.importorskip('secretstorage.exceptions')
    with pytest.raises(
        linux_secrets.SecretStoreUnavailable, match='^auth_secret_store_unavailable$'
    ):
        linux_secrets.fernet_key(
            'test',
            'account',
            create=True,
            backend=Backend(exceptions.PromptDismissedException('private')),
        )


def test_missing_backend_is_unavailable(monkeypatch):
    def missing():
        raise ImportError('private')

    monkeypatch.setattr(linux_secrets, '_backend', missing)
    with pytest.raises(
        linux_secrets.SecretStoreUnavailable, match='^auth_secret_store_unavailable$'
    ):
        linux_secrets.fernet_key('test', 'account', create=True)


@pytest.fixture
def linux(monkeypatch):
    monkeypatch.setattr(platform, 'SYSTEM', 'linux')
    backend = Backend()
    monkeypatch.setattr(linux_secrets, '_backend', lambda: backend)


def test_linux_protect_round_trips_with_stored_key(linux, monkeypatch, tmp_path):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(linux_secrets, 'fernet_key', lambda *a, **kw: key)
    first = platform.PlatformServices(tmp_path)
    token = first.protect(b'cookies')
    assert platform.PlatformServices(tmp_path).protect(token, decrypt=True) == b'cookies'
    assert first.secrets_persistent()
    assert first.session_key is None


def test_linux_protect_falls_back_to_session_key(linux, monkeypatch, tmp_path):
    def unavailable(*a, **kw):
        raise linux_secrets.SecretStoreUnavailable('auth_secret_store_unavailable')

    monkeypatch.setattr(linux_secrets, 'fernet_key', unavailable)
    service = platform.PlatformServices(tmp_path)
    assert not service.secrets_persistent()
    token = service.protect(b'cookies')
    assert service.protect(token, decrypt=True) == b'cookies'
    assert (
        platform.PlatformServices(tmp_path, session_key=service.session_key).protect(
            token, decrypt=True
        )
        == b'cookies'
    )


def test_stale_session_key_files_read_as_signed_out(linux, tmp_path):
    path = tmp_path / 'session.dat'
    first = platform.PlatformServices(tmp_path, session_key=Fernet.generate_key())
    second = platform.PlatformServices(tmp_path, session_key=Fernet.generate_key())
    atomic_protected(path, {'cookie': 'private'}, first.protect)
    assert load_protected(path, second.protect) is None
    assert b'private' not in path.read_bytes()


def test_linux_protect_errors_hide_secrets(linux, monkeypatch, tmp_path):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(linux_secrets, 'fernet_key', lambda *a, **kw: key)
    with pytest.raises(OSError, match='^auth_protection_failed$') as raised:
        platform.PlatformServices(tmp_path).protect(b'bad cookie', decrypt=True)
    assert key not in str(raised.value)
    assert raised.value.__cause__ is None


@pytest.mark.parametrize('system', ['win32', 'darwin'])
def test_secrets_persistent_true_on_windows_and_macos(monkeypatch, tmp_path, system):
    monkeypatch.setattr(platform, 'SYSTEM', system)
    assert platform.PlatformServices(tmp_path).secrets_persistent()


@pytest.mark.parametrize('temporary', [True, False])
def test_sign_in_passes_session_key_over_stdin(linux, monkeypatch, tmp_path, temporary):
    import io
    import subprocess

    from clipflow.domain.models import Service
    from clipflow.infrastructure import auth
    from tests.support.auth import Process

    gateway = auth.NativeAuthGateway(tmp_path)
    if temporary:
        gateway.platform.session_key = b'k'
    sent = []

    class Input(io.BytesIO):
        def close(self):
            sent.append(self.getvalue())
            super().close()

    calls = []

    def start(args, **kwargs):
        calls.append((args, kwargs))
        process = Process()
        process.stdin = Input() if kwargs.get('stdin') == subprocess.PIPE else None
        return process

    monkeypatch.setattr(auth.subprocess, 'Popen', start)
    gateway.sign_in(Service.YOUTUBE, 'en')
    assert ('--session-key-stdin' in calls[0][0]) is temporary
    assert sent == ([b'k\n'] if temporary else [])
