"""Opt-in native Secret Service tests, under a private D-Bus session and test keyring."""

import os
import subprocess
import sys
from uuid import uuid4

import pytest

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith('linux') or os.environ.get('CLIPFLOW_SECRET_SERVICE_NATIVE') != '1',
    reason='Run in an isolated D-Bus/gnome-keyring session with CLIPFLOW_SECRET_SERVICE_NATIVE=1',
)


def test_real_store_round_trip_and_cleanup():
    from clipflow.infrastructure.linux_secrets import _backend, fernet_key

    account = 'native-' + uuid4().hex
    backend = _backend()
    try:
        first = fernet_key('ClipFlow Tests', account, create=True)
        assert first
        assert len(first) == 44
        assert fernet_key('ClipFlow Tests', account, create=False) == first
    finally:
        backend.delete_password('ClipFlow Tests', account)
    assert fernet_key('ClipFlow Tests', account, create=False) is None


def test_no_bus_is_unavailable():
    code = """
from clipflow.infrastructure.linux_secrets import fernet_key, SecretStoreUnavailable
try:
    fernet_key('ClipFlow Tests', 'no-bus', create=False)
except SecretStoreUnavailable as error:
    assert str(error) == 'auth_secret_store_unavailable'
else:
    raise AssertionError('An absent bus was accepted')
"""
    result = subprocess.run(
        [sys.executable, '-c', code],
        env=dict(os.environ, DBUS_SESSION_BUS_ADDRESS='unix:path=/nonexistent/clipflow-test-bus'),
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
