"""Secret Service boundary: no backend exception may disclose credentials."""

from cryptography.fernet import Fernet


class SecretStoreUnavailable(OSError):
    """The session can continue, but its key cannot be persisted securely."""


def _backend():  # pragma: only linux
    from keyring.backends.SecretService import Keyring

    return Keyring()


def fernet_key(service, account, *, create, backend=None):
    try:
        store = _backend() if backend is None else backend
        key = store.get_password(service, account)
        if key is None and create:
            key = Fernet.generate_key().decode('ascii')
            store.set_password(service, account, key)
        return key
    except Exception:  # noqa: BLE001 — third-party D-Bus/backends raise varying exceptions; expose no details
        raise SecretStoreUnavailable('auth_secret_store_unavailable') from None
