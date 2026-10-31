"""Dispatch before creating a downloader window; no Tk or shared WebEngine runtime."""

import argparse
import json
import os
import platform as runtime_platform
import re
import shutil
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path

from clipflow.domain.models import Service
from clipflow.infrastructure.auth_process.sessions import AUTH_NAMES, FOLDERS
from clipflow.infrastructure.platform import PlatformServices, data_directory

FLAGS = {'--youtube-login', '--instagram-login', '--auth-self-test', '--instagram-auth-self-test'}


def _parser():
    parser = argparse.ArgumentParser()
    parser.add_argument('--youtube-login', action='store_true')
    parser.add_argument('--instagram-login', action='store_true')
    parser.add_argument('--auth-self-test', nargs='?', const='')
    parser.add_argument('--instagram-auth-self-test', nargs='?', const='')
    parser.add_argument('--language', choices=('ru', 'en'), default='ru')
    parser.add_argument('--data-dir')
    parser.add_argument('--instance-id')
    parser.add_argument('--report')
    return parser


@dataclass(frozen=True)
class _Launch:
    service: Service
    testing: bool
    root: Path
    directory: Path


def _launch(args):
    """Where this sign-in window keeps its profile, or the exit code of a refusal."""
    if args.instance_id is not None and not re.fullmatch(r'[0-9a-f]{32}', args.instance_id):
        print('FAIL invalid_instance_id')
        return 2
    instagram = args.instagram_login or args.instagram_auth_self_test is not None
    service = Service.INSTAGRAM if instagram else Service.YOUTUBE
    testing = args.auth_self_test is not None or args.instagram_auth_self_test is not None
    if testing and not os.environ.get('CLIPFLOW_DATA_DIR'):
        print('FAIL isolated_data_dir_required')
        return 2
    root = Path(args.data_dir).resolve() if args.data_dir else data_directory()
    supplied = args.instagram_auth_self_test if instagram else args.auth_self_test
    directory = Path(supplied).resolve() if testing and supplied else root / FOLDERS[service]
    if testing and (refused := _self_test_refusal(root, directory)):
        print(refused)
        return 2
    if args.report and (not testing or not Path(args.report).resolve().is_relative_to(root)):
        return 2
    return _Launch(service, testing, root, directory)


def _self_test_refusal(root, directory):
    isolated = Path(os.environ['CLIPFLOW_DATA_DIR']).expanduser().resolve()
    if not root.is_relative_to(isolated) or not directory.is_relative_to(root):
        return 'FAIL invalid_self_test_directory'
    if directory.exists() and any(directory.iterdir()):
        return 'FAIL self_test_profile_not_empty'
    return None


def _apply_logout(directory):
    """A logout request wipes the web profile before the window opens; False if unsafe."""
    if not (directory / 'logout-request').exists():
        return True
    for name in ('web-profile', 'cache'):
        path = (directory / name).resolve()
        if path.parent != directory.resolve():
            return False
        if path.is_dir():
            shutil.rmtree(path)
    (directory / 'logout-request').unlink(missing_ok=True)
    return True


def _theme_mode(root):
    try:
        preferences = json.loads((root / 'settings-v2.json').read_text(encoding='utf-8-sig'))
        mode = preferences.get('theme', 'dark') if isinstance(preferences, dict) else 'dark'
    except (OSError, ValueError):
        mode = 'dark'
    return mode if isinstance(mode, str) and mode in {'dark', 'light', 'system'} else 'dark'


def _write_report(path, data):
    Path(path).write_text(json.dumps(data), encoding='utf-8')


def _self_test_checks(window, service, platform, agent, original_icon):
    """Synthetic sign-in: modes, address privacy, protected snapshot, domain scope."""
    from PySide6.QtCore import QUrl
    from PySide6.QtNetwork import QNetworkCookie
    from PySide6.QtWebEngineCore import QWebEnginePage

    from clipflow.infrastructure.auth_process.window import USER_AGENTS

    assert agent == USER_AGENTS[window.mode.currentData()]
    assert not window.address.text().startswith('data:')
    assert window.view.page().acceptNavigationRequest(
        QUrl('https://idp.example.test/sso'),
        QWebEnginePage.NavigationType.NavigationTypeOther,
        True,
    )
    window.address_changed(
        QUrl('https://accounts.google.com/v3/signin?synthetic-private-token=value')
    )
    assert window.address.text() == 'https://accounts.google.com/v3/signin'
    cookie = QNetworkCookie(AUTH_NAMES[service][0].encode(), b'synthetic-auth-self-test')
    cookie.setDomain('.' + ('instagram.com' if service == Service.INSTAGRAM else 'youtube.com'))
    cookie.setPath('/')
    cookie.setSecure(True)
    window.cookie_added(cookie)
    assert window.write_session()
    encrypted = window.session.snapshot.read_bytes()
    assert b'synthetic-auth-self-test' not in encrypted
    assert (
        json.loads(platform.protect(encrypted, decrypt=True))[0]['name'] == AUTH_NAMES[service][0]
    )
    alien = QNetworkCookie(AUTH_NAMES[service][0].encode(), b'unrelated')
    alien.setDomain('.example.test')
    alien.setPath('/')
    window.cookie_added(alien)
    assert len(window.session_cookies()) == 1
    window.cookie_removed(alien)
    assert window.session.snapshot.read_bytes() == encrypted
    window.mode.setCurrentIndex(0)
    assert window.profile.httpUserAgent() == window.native_agent
    assert window.address.text().find('synthetic-auth-self-test') < 0
    assert not window.windowIcon().isNull() and window.windowIcon().cacheKey() == original_icon
    assert 'tkinter' not in sys.modules
    window.session.snapshot.unlink(missing_ok=True)
    window.cookies.clear()
    window.save_timer.stop()


def _start_self_test(app, window, launch, platform, theme, report):
    from PySide6.QtCore import QTimer

    from clipflow.version import APP_VERSION

    original_icon = window.windowIcon().cacheKey()

    def check(agent):
        try:
            _self_test_checks(window, launch.service, platform, agent, original_icon)
            if report:
                _write_report(
                    report,
                    {
                        'passed': True,
                        'service': launch.service.value,
                        'version': APP_VERSION,
                        'frozen': bool(getattr(sys, 'frozen', False)),
                        'rendered': True,
                        'protected_snapshot': True,
                        'os': runtime_platform.platform(),
                        'cpu': runtime_platform.machine(),
                    },
                )
            print(
                'PASS isolated WebEngine render, modes, protected compatible snapshot, '
                'domain scope, no Tk; theme=' + theme.mode
            )
            app.exit(0)
        except Exception as error:  # noqa: BLE001  # подпроект 3
            if report:
                frame = traceback.extract_tb(error.__traceback__)[-1]
                _write_report(
                    report,
                    {
                        'passed': False,
                        'error_type': type(error).__name__,
                        'function': frame.name,
                        'line': frame.lineno,
                    },
                )
            print('FAIL auth_self_test')
            app.exit(1)

    def loaded(okay):
        if not okay:
            app.exit(2)
            return
        QTimer.singleShot(
            350, lambda: window.view.page().runJavaScript('navigator.userAgent', check)
        )

    window.mode.setCurrentIndex(1)
    window.view.loadFinished.connect(loaded)
    window.view.setHtml('<html><body>ClipFlow local self-test</body></html>')
    QTimer.singleShot(25000, lambda: app.exit(2))


def main(argv=None):
    args = _parser().parse_args(sys.argv[1:] if argv is None else argv)
    launch = _launch(args)
    if isinstance(launch, int):
        return launch
    service, directory = launch.service, launch.directory
    directory.mkdir(parents=True, exist_ok=True)
    from PySide6.QtCore import QCoreApplication, QLockFile, Qt
    from PySide6.QtWidgets import QApplication

    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv[:1])
    app.setApplicationName(
        'ClipFlow ' + ('YouTube' if service == Service.YOUTUBE else 'Instagram') + ' Sign-in'
    )
    lock = QLockFile(str(directory / 'window.lock'))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        print('AUTH already_open')
        return 0
    if not _apply_logout(directory):
        print('FAIL invalid_profile_path')
        return 2
    from clipflow.infrastructure.settings import AppSettings
    from clipflow.ui.i18n import Translator
    from clipflow.ui.themes import ThemeManager

    theme = ThemeManager(app, AppSettings(language=args.language, theme=_theme_mode(launch.root)))
    translator = Translator(args.language)
    translator.install_qt()
    from clipflow.infrastructure.auth_process.window import AuthWindow

    platform = PlatformServices(launch.root)
    window = AuthWindow(
        directory,
        service,
        platform,
        translator,
        theme,
        test=launch.testing,
        instance_id=args.instance_id,
    )
    if launch.testing:
        _start_self_test(app, window, launch, platform, theme, args.report)
    window.show()
    try:
        return app.exec()
    finally:
        window.dispose()
        translator.close()
        theme.close()
        lock.unlock()


if __name__ == '__main__':
    raise SystemExit(main())
