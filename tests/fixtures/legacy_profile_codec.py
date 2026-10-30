"""Frozen 1.8.7 session wire-format reference, not an application runtime.
Copied from platform_support at 711f5a3; only synthetic profiles are allowed.
"""

import os
import sys
from pathlib import Path
from threading import Lock

if not os.environ.get('CLIPFLOW_DATA_DIR'):
    raise RuntimeError('Legacy codec fixture requires isolated test data')
APP_DATA = Path(os.environ['CLIPFLOW_DATA_DIR']).resolve()
IS_WINDOWS = sys.platform == 'win32'
IS_MAC = sys.platform == 'darwin'
_key_lock = Lock()


def protect_profile(data, decrypt=False):
    """Encrypt data with a key held in the user's macOS login Keychain."""
    if IS_WINDOWS:
        return _protect_windows(data, decrypt)
    if not IS_MAC:
        raise OSError('Saved sessions are supported on Windows and macOS.')
    from cryptography.fernet import Fernet, InvalidToken
    from keyring.backends.macOS import Keyring

    service, account = 'ClipFlow', 'profile-encryption-key-v1'
    if os.environ.get('CLIPFLOW_DATA_DIR'):
        # Test profiles must never request access to the user's real session key.
        import hashlib

        service = 'ClipFlow Tests'
        account = 'profile-key-' + hashlib.sha256(str(APP_DATA).encode()).hexdigest()[:24]
    with _key_lock:
        try:
            keychain = Keyring()
            key = keychain.get_password(service, account)
            if key is None:
                if decrypt:
                    raise ValueError('Ключ ClipFlow отсутствует в Связке ключей. Войдите заново.')
                key = Fernet.generate_key().decode('ascii')
                keychain.set_password(service, account, key)
            cipher = Fernet(key.encode('ascii'))
            return cipher.decrypt(data) if decrypt else cipher.encrypt(data)
        except InvalidToken as error:
            raise ValueError('Не удалось расшифровать профиль ClipFlow. Войдите заново.') from error
        except ValueError:
            raise
        except Exception as error:
            raise OSError('Не удалось получить доступ к Связке ключей macOS.') from error


def _protect_windows(data, decrypt=False):
    """Use the same user-scoped DPAPI format as previous Windows releases."""
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_byte))]

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    target = Blob()
    crypt32 = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    api = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    api.argtypes = [
        ctypes.POINTER(Blob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(Blob),
    ]
    api.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    if not api(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel32.LocalFree(ctypes.cast(target.data, ctypes.c_void_p))
