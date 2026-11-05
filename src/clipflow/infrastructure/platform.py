"""Native integration; retain the deployed DPAPI wire format and Keychain namespace."""

import hashlib
import os
import sys
import threading
from pathlib import Path

SYSTEM = sys.platform
_key_lock = threading.Lock()


def data_directory():
    if os.environ.get('CLIPFLOW_DATA_DIR'):
        return Path(os.environ['CLIPFLOW_DATA_DIR']).expanduser().resolve()
    if SYSTEM == 'darwin':
        return Path.home() / 'Library/Application Support/ClipFlow'
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'ClipFlow'


class PlatformServices:
    def __init__(self, data_dir=None):
        self.data_dir = Path(data_dir or data_directory()).expanduser().resolve()

    def key_namespace(self):
        if os.environ.get('CLIPFLOW_DATA_DIR'):
            return 'ClipFlow Tests', 'profile-key-' + hashlib.sha256(
                str(self.data_dir).encode()
            ).hexdigest()[:24]
        return 'ClipFlow', 'profile-encryption-key-v1'

    def protect(self, data: bytes, decrypt=False):
        try:
            if SYSTEM == 'win32':
                return _protect_windows(data, decrypt)
            if SYSTEM != 'darwin':
                raise OSError
            from cryptography.fernet import Fernet
            from keyring.backends.macOS import Keyring

            service, account = self.key_namespace()
            with _key_lock:
                keychain = Keyring()
                key = keychain.get_password(service, account)
                if key is None:
                    if decrypt:
                        raise ValueError
                    key = Fernet.generate_key().decode('ascii')
                    keychain.set_password(service, account, key)
                cipher = Fernet(key.encode('ascii'))
                return cipher.decrypt(data) if decrypt else cipher.encrypt(data)
        except Exception:  # noqa: BLE001  # keyring и cryptography: наружу только безопасный код, без ключей
            raise OSError('auth_protection_failed') from None

    def reveal(self, path: Path):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        path = Path(path).resolve()
        target = path if path.is_dir() else path.parent
        if not target.is_dir() or not QDesktopServices.openUrl(QUrl.fromLocalFile(str(target))):
            raise OSError('folder_missing')

    def choose_folder(self, parent, initial: Path):
        from PySide6.QtWidgets import QFileDialog

        result = QFileDialog.getExistingDirectory(parent, 'ClipFlow', str(initial))
        return Path(result).resolve() if result else None


def _protect_windows(data, decrypt=False):  # pragma: only windows
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
