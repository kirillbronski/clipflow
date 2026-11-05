"""Sessions sealed in tests use real Keychain keys under 'ClipFlow Tests'; remove them afterwards.

Only this exact service is touched: the app's own key lives under 'ClipFlow'. Keys are deleted
through keyring from the Python that created them, so macOS asks nothing; keys another program
created (a packaged build's self-test) cannot be deleted this way and are left as they are.
"""

import re
import subprocess
import sys

SERVICE = 'ClipFlow Tests'
_ITEM = re.compile(r'"acct"<blob>="([^"]*)".*?"svce"<blob>="([^"]*)"', re.DOTALL)


def _test_accounts():
    """Accounts of the test service; dump-keychain without -d lists attributes, never secrets."""
    dump = subprocess.run(
        ['security', 'dump-keychain'], capture_output=True, text=True, timeout=60
    ).stdout
    items = dump.split('keychain: ')
    return [m.group(1) for item in items if (m := _ITEM.search(item)) and m.group(2) == SERVICE]


def forget_test_keys():
    """Delete the test keys this Python may delete; return (removed, left) — (0, 0) off macOS."""
    if sys.platform != 'darwin':
        return 0, 0
    from keyring.backends.macOS import Keyring
    from keyring.errors import KeyringError

    keychain = Keyring()
    removed = left = 0
    for account in _test_accounts():
        try:
            keychain.delete_password(SERVICE, account)
            removed += 1
        except KeyringError:  # another program's key, or the Keychain is locked
            left += 1
    return removed, left
