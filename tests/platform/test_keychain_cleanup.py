"""Test runs leave no sealing keys behind in the developer's Keychain."""

import sys

import pytest

from tests.support.keychain import forget_test_keys

pytestmark = pytest.mark.skipif(sys.platform != 'darwin', reason='macOS Keychain only')


def test_cleanup_removes_test_keys_and_keeps_other_services():
    from keyring.backends.macOS import Keyring

    keychain = Keyring()
    keychain.set_password('ClipFlow Tests', 'profile-key-cleanup-probe', 'secret')
    keychain.set_password('ClipFlow Tests Keep', 'profile-key-cleanup-probe', 'secret')
    try:
        removed, _ = forget_test_keys()
        assert removed >= 1
        assert keychain.get_password('ClipFlow Tests', 'profile-key-cleanup-probe') is None
        assert keychain.get_password('ClipFlow Tests Keep', 'profile-key-cleanup-probe')
    finally:
        keychain.delete_password('ClipFlow Tests Keep', 'profile-key-cleanup-probe')
