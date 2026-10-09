"""macOS integration shared by the downloader and sign-in process."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
from contextlib import contextmanager

IS_MAC = sys.platform == 'darwin'
RESOURCE_DIR = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
APP_DATA = (Path.home() / 'Library/Application Support/ClipFlow' if IS_MAC
            else Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'ClipFlow')
AUTH_DIR = APP_DATA / 'YouTubeAuth'
if os.environ.get('CLIPFLOW_DATA_DIR'):
    APP_DATA = Path(os.environ['CLIPFLOW_DATA_DIR']).expanduser().resolve()
    AUTH_DIR = APP_DATA / 'YouTubeAuth'
FONT_FAMILY = 'Helvetica Neue' if IS_MAC else 'Segoe UI'
MODIFIER = 'Command' if IS_MAC else 'Control'
CONTEXT_BUTTON = 'Button-2' if IS_MAC else 'Button-3'
_key_lock = threading.Lock()
_appkit = None


@contextmanager
def atomic_redraw(root):
    """Keep Tk's intermediate idle redraws off screen until the batch is ready."""
    global _appkit
    if not IS_MAC or not root.winfo_ismapped():
        yield
        return
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError('Screen updates must be batched on the UI thread')
    if _appkit is None:
        import ctypes
        _appkit = ctypes.CDLL('/System/Library/Frameworks/AppKit.framework/AppKit')
        for name in ('NSDisableScreenUpdates', 'NSEnableScreenUpdates'):
            function = getattr(_appkit, name)
            function.argtypes = []
            function.restype = None
    _appkit.NSDisableScreenUpdates()
    try:
        yield
        root.update_idletasks()
    finally:
        _appkit.NSEnableScreenUpdates()


def binary_path(name):
    candidate = RESOURCE_DIR / 'bin' / name
    if candidate.is_file():
        return str(candidate)
    for directory in ('/opt/homebrew/bin', '/usr/local/bin'):
        candidate = Path(directory) / name
        if candidate.is_file():
            return str(candidate)
    return shutil.which(name)


def open_folder(path):
    if IS_MAC:
        subprocess.Popen(['/usr/bin/open', str(path)])
    else:
        os.startfile(str(path))


def protect_profile(data, decrypt=False):
    """Encrypt data with a key held in the user's macOS login Keychain."""
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
