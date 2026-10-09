"""Embedded YouTube sign-in window for ClipFlow."""
from platform_support import AUTH_DIR, APP_DATA, RESOURCE_DIR, protect_profile as protect
import json
import os
from pathlib import Path
import sys
import time

from PySide6.QtCore import QUrl, QTimer, Qt, QDateTime, QCoreApplication, QEvent
from PySide6.QtGui import QIcon
from PySide6.QtNetwork import QNetworkCookie
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QTabWidget, QMessageBox
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView

from version import APP_VERSION as VERSION
USER_AGENTS = {
    'Chrome на iPad · 51': 'Mozilla/5.0 (iPad; CPU OS 13_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/51.0.2704.84 Mobile/15E148 Safari/604.1',
    'Chrome на iPad · 87': 'Mozilla/5.0 (iPad; CPU OS 13_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/87.0.4280.88 Mobile/15E148 Safari/604.1',
    'Обычный Qt WebEngine': None,
}
LOGIN_URL = 'https://accounts.google.com/ServiceLogin?service=youtube&uilel=3&passive=true&continue=https%3A%2F%2Fwww.youtube.com%2Fsignin%3Faction_handle_signin%3Dtrue%26app%3Dm%26hl%3Den%26next%3D%252F&hl=en'
ROOT = AUTH_DIR

SERVICE = 'YouTube'
DOMAIN = 'youtube.com'
AUTH_NAMES = ('SAPISID','__Secure-3PAPISID','__Secure-1PAPISID')

def configure_service(service):
    global SERVICE, DOMAIN, AUTH_NAMES, ROOT, LOGIN_URL
    SERVICE = service
    if service == 'Instagram':
        DOMAIN = 'instagram.com'
        AUTH_NAMES = ('sessionid',)
        ROOT = APP_DATA / 'InstagramAuth'
        LOGIN_URL = 'https://www.instagram.com/accounts/login/'


LANGUAGE = 'ru'
TEXTS = {
 'Вход пока не подтверждён':'Not signed in yet', 'Войти в Google':'Sign in with Google',
 'YouTube':'YouTube', 'Сохранить сессию':'Save session', 'Выйти':'Sign out',
 'Обычный Qt WebEngine':'Standard Qt WebEngine', 'Chrome на iPad · 51':'Chrome on iPad · 51',
 'Chrome на iPad · 87':'Chrome on iPad · 87', 'Страница не открыта':'No page open',
 'Страница загружена':'Page loaded', 'Вход Google':'Google sign-in',
 'Страница не загрузилась. Проверьте подключение.':'Page did not load. Check your connection.',
 'Google отклонил вход. Можно проверить другой режим браузера.':'Google rejected the sign-in. You can try another browser mode.',
 'Режим изменён. Нажмите «Войти в Google», чтобы открыть страницу заново.':'Mode changed. Click Sign in with Google to open the page again.',
 'Сессия YouTube ещё не обнаружена. После входа откройте YouTube.':'YouTube session not detected yet. Open YouTube after signing in.',
 'Сессия YouTube сохранена с защитой macOS Keychain. ClipFlow использует этот аккаунт.':'YouTube session saved with macOS Keychain protection. ClipFlow can now use this account.',
 'Сессия YouTube удалена':'YouTube session removed',
 'Окно входа уже открыто. Вернитесь в него.':'The sign-in window is already open. Return to that window.',
 'Войдите на странице Google, затем откройте YouTube и нажмите «Сохранить сессию».\nСохранённый вход используется для скачивания в ClipFlow.':'Sign in on the Google page, then open YouTube and click Save session.\nClipFlow uses this session for downloads.',
}
def tr(text):
    if SERVICE == 'Instagram':
        if text.startswith('Войдите на странице Google'):
            return 'Войдите на странице Instagram. Сессия сохраняется автоматически и используется для скачивания в ClipFlow.' if LANGUAGE != 'en' else 'Sign in on the Instagram page. Your session is saved automatically for ClipFlow downloads.'
        if LANGUAGE != 'en':return text.replace('YouTube / Google','Instagram').replace('YouTube','Instagram').replace('Google','Instagram')
        text = TEXTS.get(text,text).replace('YouTube','Instagram').replace('Google','Instagram')
        return text.replace('Вход в Instagram · ClipFlow ','Instagram sign-in · ClipFlow ').replace('ClipFlow — вход в Instagram · ','ClipFlow — Instagram sign-in · ')
    if LANGUAGE!='en':return text
    return TEXTS.get(text,text.replace('Вход в YouTube · ClipFlow ','YouTube sign-in · ClipFlow ').replace('ClipFlow — вход в YouTube · ','ClipFlow — YouTube sign-in · '))
_BaseLabel=QLabel
class QLabel(_BaseLabel):
    def __init__(self,text='',*args,**kwargs):super().__init__(tr(text),*args,**kwargs)
    def setText(self,text):super().setText(tr(text))
_BaseButton=QPushButton
class QPushButton(_BaseButton):
    def __init__(self,text='',*args,**kwargs):super().__init__(tr(text),*args,**kwargs)
_BaseCombo=QComboBox
class QComboBox(_BaseCombo):
    def addItems(self,items):
        for item in items:self.addItem(tr(item),item)
    def currentText(self):return self.currentData() or super().currentText()
    def setCurrentText(self,text):
        index=self.findData(text)
        if index>=0:self.setCurrentIndex(index)

class Page(QWebEnginePage):
    def __init__(self, window):
        super().__init__(window.profile, window)
        self.window = window
    def createWindow(self, kind):
        return self.window.add_tab('Вход Google').page()
    def acceptNavigationRequest(self, url, kind, main):
        if main and url.scheme() not in ('https', 'about', 'data'):
            return False
        return super().acceptNavigationRequest(url, kind, main)

class Window(QMainWindow):
    def __init__(self, directory=None, test=False):
        super().__init__()
        self.directory = Path(directory or ROOT).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.settings_file = self.directory/'settings.json'
        try:
            self.settings = json.loads(self.settings_file.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            self.settings = {}
        self.cookies = {}
        self.setWindowTitle(tr('ClipFlow — вход в YouTube · ' + VERSION))
        self.resize(1100, 850)
        self.setMinimumSize(800, 600)
        icon = RESOURCE_DIR / ('clipflow-instagram.png' if SERVICE == 'Instagram' else 'clipflow.png')
        if icon.is_file():self.setWindowIcon(QIcon(str(icon)))
        widget = QWidget();self.setCentralWidget(widget)
        layout = QVBoxLayout(widget)
        title = QLabel('Вход в YouTube · ClipFlow ' + VERSION)
        title.setStyleSheet('font-size:22px;font-weight:600;padding:8px')
        layout.addWidget(title)
        note = QLabel('Войдите на странице Google, затем откройте YouTube и нажмите «Сохранить сессию».\nСохранённый вход используется для скачивания в ClipFlow.')
        note.setWordWrap(True);layout.addWidget(note)
        controls = QHBoxLayout();layout.addLayout(controls)
        self.mode = QComboBox();self.mode.addItems(USER_AGENTS)
        chosen=self.settings.get('mode','Обычный Qt WebEngine')
        if chosen in USER_AGENTS:self.mode.setCurrentText(chosen)
        controls.addWidget(self.mode)
        if SERVICE == 'Instagram':
            self.mode.setCurrentText('Обычный Qt WebEngine')
            self.mode.hide()
        for caption, callback in [('Войти в Google',self.login),('YouTube',self.youtube),('Сохранить сессию',self.save_session),('Выйти',self.logout)]:
            button=QPushButton(caption);button.clicked.connect(callback);controls.addWidget(button)
        self.mode.currentTextChanged.connect(self.change_mode)
        self.address=QLabel('Страница не открыта');self.address.setTextInteractionFlags(Qt.TextSelectableByMouse);layout.addWidget(self.address)
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        self.status=QLabel('Вход пока не подтверждён');layout.addWidget(self.status)
        self.save_timer=QTimer(self);self.save_timer.setSingleShot(True);self.save_timer.timeout.connect(self.write_session)
        self.logout_timer=QTimer(self);self.logout_timer.timeout.connect(self.check_logout_request);self.logout_timer.start(300)
        self.profile=QWebEngineProfile('clipflow-auth-prototype',self)
        self.profile.setPersistentStoragePath(str(self.directory/'web-profile'))
        self.profile.setCachePath(str(self.directory/'cache'))
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)
        self.native_agent=self.profile.httpUserAgent()
        self.apply_mode()
        self.store=self.profile.cookieStore()
        self.store.cookieAdded.connect(self.cookie_added)
        self.store.cookieRemoved.connect(self.cookie_removed)
        self.store.loadAllCookies()
        self.view=self.add_tab('YouTube / Google')
        self.setStyleSheet('QWidget{background:#161616;color:#f4eeee;font-family:Helvetica Neue;font-size:13px} QPushButton,QComboBox{background:#332929;padding:9px;border:1px solid #665252;border-radius:8px} QPushButton:hover{background:#554040} QTabBar::tab{padding:8px;background:#332929} QTabBar::tab:selected{background:#b50000}')
        if SERVICE == 'Instagram':
            self.setStyleSheet(self.styleSheet().replace('#b50000','#C13584').replace('#332929','#30232F').replace('#554040','#643052'))
        if not test:
            self.view.setHtml('<html><body style="background:#202020;color:white;font:18px sans-serif;padding:40px"><h2>Проверка входа YouTube</h2><p>Нажмите «Войти в Google» сверху.</p><p>Пароль вводится непосредственно на странице Google.</p></body></html>')
    def add_tab(self,title):
        view=QWebEngineView(self);page=Page(self);view.setPage(page)
        self.tabs.addTab(view,tr(title));self.tabs.setCurrentWidget(view)
        view.urlChanged.connect(lambda url:self.address_changed(url))
        view.loadFinished.connect(lambda okay:self.page_loaded(view,okay))
        return view
    def page_loaded(self,view,okay):
        url=view.url()
        if url.host().endswith('google.com') and '/rejected' in url.path():
            self.status.setText('Google отклонил вход. Можно проверить другой режим браузера.')
        else:
            self.status.setText('Страница загружена' if okay else 'Страница не загрузилась. Проверьте подключение.')
    def address_changed(self,url):
        # Display the trusted origin/path, never authentication query values.
        self.address.setText(url.scheme()+'://'+url.host()+url.path())
        if url.host().endswith('google.com') and '/rejected' in url.path():
            self.status.setText('Google отклонил вход. Можно проверить другой режим браузера.')
    def current_view(self):return self.tabs.currentWidget()
    def apply_mode(self):self.profile.setHttpUserAgent(USER_AGENTS[self.mode.currentText()] or self.native_agent)
    def change_mode(self):
        self.apply_mode();self.settings['mode']=self.mode.currentText()
        self.settings_file.write_text(json.dumps(self.settings,ensure_ascii=False),encoding='utf-8')
        self.status.setText('Режим изменён. Нажмите «Войти в Google», чтобы открыть страницу заново.')
    def login(self):self.current_view().setUrl(QUrl(LOGIN_URL))
    def youtube(self):self.current_view().setUrl(QUrl('https://www.'+DOMAIN+'/'))
    def cookie_key(self,cookie):return (cookie.domain(),cookie.path(),bytes(cookie.name()))
    def cookie_added(self,cookie):
        domain=cookie.domain().lstrip('.').lower()
        if domain==DOMAIN or domain.endswith('.'+DOMAIN):
            self.cookies[self.cookie_key(cookie)]=QNetworkCookie(cookie)
            self.save_timer.start(250)
    def cookie_removed(self,cookie):
        self.cookies.pop(self.cookie_key(cookie),None)
        if bytes(cookie.name()).decode() in AUTH_NAMES:
            (self.directory/'session.dat').unlink(missing_ok=True)
        self.save_timer.start(250)
    def session_cookies(self):
        now=time.time();result=[]
        for cookie in self.cookies.values():
            expiry=-1 if cookie.isSessionCookie() else cookie.expirationDate().toSecsSinceEpoch()
            if expiry>=0 and expiry<=now:continue
            result.append({'domain':cookie.domain(),'path':cookie.path(),'name':bytes(cookie.name()).decode(),'value':bytes(cookie.value()).decode(),'secure':cookie.isSecure(),'httpOnly':cookie.isHttpOnly(),'expires':expiry})
        return result
    def write_session(self):
        if (self.directory/'logout-request').exists():return False
        cookies=self.session_cookies()
        if not any(c['name'] in AUTH_NAMES and c['value'] for c in cookies):
            return False
        temporary=self.directory/'session.tmp'
        temporary.write_bytes(protect(json.dumps(cookies).encode('utf-8')))
        os.replace(temporary,self.directory/'session.dat')
        return True
    def save_session(self):
        if self.write_session():
            self.status.setText('Сессия YouTube сохранена с защитой macOS Keychain. ClipFlow использует этот аккаунт.')
        else:
            self.status.setText('Сессия YouTube ещё не обнаружена. После входа откройте YouTube.')
    def logout(self):
        self.store.deleteAllCookies();self.cookies.clear();self.profile.clearHttpCache()
        (self.directory/'session.dat').unlink(missing_ok=True)
        self.youtube();self.status.setText('Сессия YouTube удалена')
    def check_logout_request(self):
        marker=self.directory/'logout-request'
        if marker.exists():
            marker.unlink(missing_ok=True)
            self.logout()
            self.close()
    def closeEvent(self,event):
        self.write_session()
        super().closeEvent(event)
    def dispose(self):
        # Destroy pages before their shared profile so Chromium flushes the profile.
        for index in range(self.tabs.count()):
            view=self.tabs.widget(index)
            view.stop()
            view.page().deleteLater()
            view.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
        self.profile.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

def self_test(application, directory):
    window=Window(directory,test=True)
    window.mode.setCurrentIndex(0)
    failed=[]
    def loaded(okay):
        if not okay:failed.append('HTML load failed');application.exit(1);return
        def checked(agent):
            try:
                assert agent==USER_AGENTS[window.mode.currentText()]
                cookie=QNetworkCookie(AUTH_NAMES[0].encode(),b'prototype-fake-cookie')
                cookie.setDomain('.'+DOMAIN);cookie.setPath('/');cookie.setSecure(True)
                window.cookie_added(cookie)
                assert window.write_session()
                encoded=(window.directory/'session.dat').read_bytes()
                assert b'prototype-fake-cookie' not in encoded
                assert json.loads(protect(encoded,decrypt=True))[0]['name']==AUTH_NAMES[0]
                unrelated=QNetworkCookie(b'SAPISID',b'fake');unrelated.setDomain('.example.com')
                window.cookie_added(unrelated);assert len(window.session_cookies())==1
                window.mode.setCurrentText('Обычный Qt WebEngine')
                assert window.profile.httpUserAgent()==window.native_agent
                (window.directory/'session.dat').unlink();window.cookies.clear()
                print('PASS Qt WebEngine renders page; iPad UA; Keychain-encrypted snapshot; domain scope; native UA; settings')
                application.exit(0)
            except Exception as error:
                print('FAIL',type(error).__name__,str(error));application.exit(1)
        window.view.page().runJavaScript('navigator.userAgent',checked)
    window.view.loadFinished.connect(loaded)
    window.view.setHtml('<html><body>ClipFlow self test</body></html>')
    QTimer.singleShot(20000,lambda:application.exit(2))
    result=application.exec()
    window.dispose()
    return result

def main():
    global LANGUAGE
    if '--instagram-login' in sys.argv or '--instagram-auth-self-test' in sys.argv:configure_service('Instagram')
    if '--language' in sys.argv:
        index=sys.argv.index('--language')
        LANGUAGE=sys.argv[index+1] if index+1<len(sys.argv) else 'ru'
    application=QApplication(sys.argv)
    application.setApplicationName('ClipFlow ' + SERVICE + ' Sign-in')
    if '--auth-self-test' in sys.argv or '--instagram-auth-self-test' in sys.argv:
        return self_test(application,sys.argv[-1])
    from PySide6.QtCore import QLockFile
    ROOT.mkdir(parents=True,exist_ok=True)
    lock=QLockFile(str(ROOT/'window.lock'))
    if not lock.tryLock(0):
        QMessageBox.information(None,'ClipFlow',tr('Окно входа уже открыто. Вернитесь в него.'))
        return 0
    marker=ROOT/'logout-request'
    if marker.exists():
        marker.unlink(missing_ok=True)
        # Clear only this app's persistent profile after a sign-out while it was closed.
        import shutil
        for name in ('web-profile','cache'):
            path=(ROOT/name).resolve()
            if path.parent==ROOT.resolve():shutil.rmtree(path,ignore_errors=True)
    window=Window(ROOT)
    if '--auth-logout' in sys.argv:
        window.logout();window.dispose();return 0
    window.show()
    window.youtube()
    result=application.exec()
    window.dispose()
    lock.unlock()
    return result

if __name__=='__main__':
    raise SystemExit(main())
