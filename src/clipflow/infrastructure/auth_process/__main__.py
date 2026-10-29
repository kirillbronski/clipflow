"""Dispatch before creating a downloader window; no Tk or shared WebEngine runtime."""
import argparse
import json
import os
import re
from pathlib import Path
import shutil
import sys

from clipflow.domain.models import Service
from clipflow.infrastructure.platform import PlatformServices,data_directory
from clipflow.infrastructure.auth_process.sessions import FOLDERS,AUTH_NAMES

FLAGS={'--youtube-login','--instagram-login','--auth-self-test','--instagram-auth-self-test'}


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--youtube-login',action='store_true'); parser.add_argument('--instagram-login',action='store_true')
    parser.add_argument('--auth-self-test',nargs='?',const=''); parser.add_argument('--instagram-auth-self-test',nargs='?',const='')
    parser.add_argument('--language',choices=('ru','en'),default='ru'); parser.add_argument('--data-dir')
    parser.add_argument('--instance-id')
    args=parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.instance_id is not None and not re.fullmatch(r'[0-9a-f]{32}',args.instance_id):
        print('FAIL invalid_instance_id'); return 2
    instagram=args.instagram_login or args.instagram_auth_self_test is not None
    service=Service.INSTAGRAM if instagram else Service.YOUTUBE
    testing=args.auth_self_test is not None or args.instagram_auth_self_test is not None
    if testing and not os.environ.get('CLIPFLOW_DATA_DIR'):
        print('FAIL isolated_data_dir_required'); return 2
    root=Path(args.data_dir).resolve() if args.data_dir else data_directory()
    supplied=args.instagram_auth_self_test if instagram else args.auth_self_test
    directory=Path(supplied).resolve() if testing and supplied else root/FOLDERS[service]
    if testing:
        isolated=Path(os.environ['CLIPFLOW_DATA_DIR']).expanduser().resolve()
        if not root.is_relative_to(isolated) or not directory.is_relative_to(root):
            print('FAIL invalid_self_test_directory'); return 2
        if directory.exists() and any(directory.iterdir()):
            print('FAIL self_test_profile_not_empty'); return 2
    directory.mkdir(parents=True,exist_ok=True)
    from PySide6.QtCore import QLockFile,Qt,QCoreApplication,QTimer
    from PySide6.QtWidgets import QApplication
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app=QApplication(sys.argv[:1]); app.setApplicationName('ClipFlow '+('YouTube' if service==Service.YOUTUBE else 'Instagram')+' Sign-in')
    lock=QLockFile(str(directory/'window.lock')); lock.setStaleLockTime(0)
    if not lock.tryLock(0): print('AUTH already_open'); return 0
    if (directory/'logout-request').exists():
        for name in ('web-profile','cache'):
            path=(directory/name).resolve()
            if path.parent!=directory.resolve(): print('FAIL invalid_profile_path'); return 2
            if path.is_dir(): shutil.rmtree(path)
        (directory/'logout-request').unlink(missing_ok=True)
    from clipflow.infrastructure.settings import AppSettings
    from clipflow.ui.i18n import Translator
    from clipflow.ui.themes import ThemeManager
    try:
        preferences=json.loads((root/'settings-v2.json').read_text(encoding='utf-8-sig'))
        mode=preferences.get('theme','dark') if isinstance(preferences,dict) else 'dark'
    except (OSError,ValueError): mode='dark'
    if not isinstance(mode,str) or mode not in {'dark','light','system'}: mode='dark'
    theme=ThemeManager(app,AppSettings(language=args.language,theme=mode)); translator=Translator(args.language); translator.install_qt()
    from clipflow.infrastructure.auth_process.window import AuthWindow,USER_AGENTS
    platform=PlatformServices(root); window=AuthWindow(directory,service,platform,translator,theme,test=testing,instance_id=args.instance_id)
    if testing:
        from PySide6.QtNetwork import QNetworkCookie
        original_icon=window.windowIcon().cacheKey()
        def loaded(okay):
            if not okay: app.exit(2); return
            def check(agent):
                try:
                    assert agent==USER_AGENTS[window.mode.currentData()]
                    assert not window.address.text().startswith('data:')
                    from PySide6.QtCore import QUrl
                    from PySide6.QtWebEngineCore import QWebEnginePage
                    assert window.view.page().acceptNavigationRequest(QUrl('https://idp.example.test/sso'),QWebEnginePage.NavigationType.NavigationTypeOther,True)
                    window.address_changed(QUrl('https://accounts.google.com/v3/signin?synthetic-private-token=value'))
                    assert window.address.text()=='https://accounts.google.com/v3/signin'
                    cookie=QNetworkCookie(AUTH_NAMES[service][0].encode(),b'synthetic-auth-self-test')
                    cookie.setDomain('.'+('instagram.com' if instagram else 'youtube.com')); cookie.setPath('/'); cookie.setSecure(True)
                    window.cookie_added(cookie); assert window.write_session()
                    encrypted=window.session.snapshot.read_bytes(); assert b'synthetic-auth-self-test' not in encrypted
                    assert json.loads(platform.protect(encrypted,decrypt=True))[0]['name']==AUTH_NAMES[service][0]
                    alien=QNetworkCookie(AUTH_NAMES[service][0].encode(),b'unrelated'); alien.setDomain('.example.test'); alien.setPath('/')
                    window.cookie_added(alien); assert len(window.session_cookies())==1
                    window.cookie_removed(alien); assert window.session.snapshot.read_bytes()==encrypted
                    window.mode.setCurrentIndex(0); assert window.profile.httpUserAgent()==window.native_agent
                    assert window.address.text().find('synthetic-auth-self-test')<0
                    assert not window.windowIcon().isNull() and window.windowIcon().cacheKey()==original_icon
                    assert 'tkinter' not in sys.modules
                    window.session.snapshot.unlink(missing_ok=True); window.cookies.clear(); window.save_timer.stop()
                    print('PASS isolated WebEngine render, modes, protected compatible snapshot, domain scope, no Tk; theme='+theme.mode); app.exit(0)
                except Exception: print('FAIL auth_self_test'); app.exit(1)
            QTimer.singleShot(350,lambda:window.view.page().runJavaScript('navigator.userAgent',check))
        window.mode.setCurrentIndex(1)
        window.view.loadFinished.connect(loaded); window.view.setHtml('<html><body>ClipFlow local self-test</body></html>')
        QTimer.singleShot(25000,lambda:app.exit(2))
    window.show()
    try: return app.exec()
    finally:
        window.dispose(); translator.close(); theme.close(); lock.unlock()


if __name__=='__main__': raise SystemExit(main())
