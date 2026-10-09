"""Platform integration shared by the downloader and sign-in process."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
from contextlib import contextmanager

IS_MAC = sys.platform == 'darwin'
IS_WINDOWS = sys.platform == 'win32'
RESOURCE_DIR = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
APP_DATA = (Path.home() / 'Library/Application Support/ClipFlow' if IS_MAC
            else Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'ClipFlow')
# Keep Windows settings/GetCourse credentials at their historical location.
SETTINGS_DIR = (Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'YouTubeDownloader'
                if IS_WINDOWS else APP_DATA)
AUTH_DIR = APP_DATA / 'YouTubeAuth'
if os.environ.get('CLIPFLOW_DATA_DIR'):
    APP_DATA = Path(os.environ['CLIPFLOW_DATA_DIR']).expanduser().resolve()
    AUTH_DIR = APP_DATA / 'YouTubeAuth'
    SETTINGS_DIR = APP_DATA
PROTECTION_NAME = 'macOS Keychain' if IS_MAC else 'Windows DPAPI'
SHORTCUT_LABEL = '⌘' if IS_MAC else 'Ctrl'
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
    executable = name + ('.exe' if IS_WINDOWS else '')
    project = Path(__file__).resolve().parents[1]
    directories = [RESOURCE_DIR / 'bin', Path(sys.executable).parent,
                   project / '.runtime' / ('windows' if IS_WINDOWS else 'macos') / 'bin']
    if os.environ.get('CLIPFLOW_BIN_DIR'):
        directories.insert(0, Path(os.environ['CLIPFLOW_BIN_DIR']).expanduser())
    if IS_MAC:
        directories.extend([Path('/opt/homebrew/bin'), Path('/usr/local/bin')])
    for directory in directories:
        candidate = directory / executable
        if candidate.is_file():
            return str(candidate)
    return shutil.which(executable)


def open_folder(path):
    if IS_MAC:
        subprocess.Popen(['/usr/bin/open', str(path)])
    else:
        os.startfile(str(path))


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
    api.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                    ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    api.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    if not api(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel32.LocalFree(ctypes.cast(target.data, ctypes.c_void_p))


def platform_text(text):
    """Display native shortcut and credential-protection names in shared UI."""
    return text.replace('macOS Keychain', PROTECTION_NAME).replace('⌘', SHORTCUT_LABEL)
