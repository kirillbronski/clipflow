"""Interactive sign-in in its own process; passwords are entered on provider pages."""
import json
from pathlib import Path
import time

from PySide6.QtCore import Qt,QTimer,QUrl,QCoreApplication,QEvent
from PySide6.QtNetwork import QNetworkCookie
from PySide6.QtWidgets import QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,QTabWidget
from PySide6.QtWebEngineCore import QWebEngineProfile,QWebEnginePage,QWebEngineUrlRequestInterceptor
from PySide6.QtWebEngineWidgets import QWebEngineView

from clipflow.domain.models import Service
from clipflow.infrastructure.auth_process.sessions import DOMAINS,AUTH_NAMES,SessionStore
from clipflow.ui.themes import application_icon

USER_AGENTS={
 'Обычный Qt WebEngine':None,
 'Chrome на iPad · 51':'Mozilla/5.0 (iPad; CPU OS 13_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/51.0.2704.84 Mobile/15E148 Safari/604.1',
 'Chrome на iPad · 87':'Mozilla/5.0 (iPad; CPU OS 13_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/87.0.4280.88 Mobile/15E148 Safari/604.1',
}
LOGIN_URL='https://accounts.google.com/ServiceLogin?service=youtube&uilel=3&passive=true&continue=https%3A%2F%2Fwww.youtube.com%2Fsignin%3Faction_handle_signin%3Dtrue%26app%3Dm%26hl%3Den%26next%3D%252F&hl=en'


class LocalOnly(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self,info):
        if info.requestUrl().scheme() not in {'data','about','qrc'}: info.block(True)


class Page(QWebEnginePage):
    def __init__(self,window,view): super().__init__(window.profile,view); self.window=window
    def createWindow(self,kind): return self.window.add_tab().page()
    def acceptNavigationRequest(self,url,kind,main):
        if main and url.scheme() not in {'https','about','data'}: return False
        if main and url.scheme()=='https' and url.userInfo(): return False
        return super().acceptNavigationRequest(url,kind,main)


class AuthWindow(QMainWindow):
    def __init__(self,directory,service,platform,translator,theme,*,test=False,instance_id=None):
        super().__init__(); self.directory=Path(directory); self.service=service; self.tr=translator; self.theme=theme
        self.directory.mkdir(parents=True,exist_ok=True); self.session=SessionStore(self.directory,service,platform.protect)
        self.close_path=self.directory/('close-request-'+instance_id) if instance_id else None
        self.cookies={}; self._disposing=False; self._logged_out=False; self.settings_file=self.directory/'settings.json'
        try: settings=json.loads(self.settings_file.read_text(encoding='utf-8'))
        except (OSError,ValueError): settings={}
        chosen=settings.get('mode') if isinstance(settings,dict) else None
        self.service_name='YouTube' if service==Service.YOUTUBE else 'Instagram'
        self.setWindowTitle(self.tr.text('auth_window_title',service=self.service_name)); self.resize(1100,800); self.setMinimumSize(800,600)
        self.setWindowIcon(application_icon())
        root=QWidget(); root.setObjectName('root'); self.setCentralWidget(root); layout=QVBoxLayout(root)
        heading=QLabel(self.tr.text('auth_window_title',service=self.service_name)); layout.addWidget(heading)
        note=self.tr.widget(QLabel,'auth_embedded_note'); note.setWordWrap(True); layout.addWidget(note)
        controls=QHBoxLayout(); self.mode=QComboBox()
        for key,label in [('Обычный Qt WebEngine','auth_native_mode'),('Chrome на iPad · 51','auth_ipad51'),('Chrome на iPad · 87','auth_ipad87')]: self.mode.addItem(self.tr.text(label),key)
        self.mode.setCurrentIndex(max(0,self.mode.findData(chosen))); controls.addWidget(self.mode)
        if service==Service.INSTAGRAM: self.mode.setCurrentIndex(0); self.mode.hide()
        for key,callback in [('sign_in',self.login),('open_service',self.open_service),('save_session',self.save_session),('sign_out',self.logout)]:
            button=self.tr.widget(QPushButton,key); button.clicked.connect(callback); controls.addWidget(button)
        layout.addLayout(controls); self.address=QLabel(); self.address.setTextFormat(Qt.TextFormat.PlainText); self.address.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse); layout.addWidget(self.address)
        self.tabs=QTabWidget(); layout.addWidget(self.tabs,1); self.status=self.tr.widget(QLabel,'not_signed_in'); self.status.setWordWrap(True); layout.addWidget(self.status)
        # Preserve the existing Chromium profile name and paths, independently per service.
        self.profile=QWebEngineProfile('clipflow-auth-prototype',self)
        self.profile.setPersistentStoragePath(str(self.directory/'web-profile')); self.profile.setCachePath(str(self.directory/'cache'))
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        self.native_agent=self.profile.httpUserAgent(); self.apply_mode()
        if test:
            self.interceptor=LocalOnly(self.profile); self.profile.setUrlRequestInterceptor(self.interceptor)
        self.store=self.profile.cookieStore(); self.store.cookieAdded.connect(self.cookie_added); self.store.cookieRemoved.connect(self.cookie_removed)
        self.save_timer=QTimer(self); self.save_timer.setSingleShot(True); self.save_timer.timeout.connect(self.write_session)
        self.marker_timer=QTimer(self); self.marker_timer.setInterval(200); self.marker_timer.timeout.connect(self._markers); self.marker_timer.start()
        self.view=self.add_tab(); self.mode.currentIndexChanged.connect(self.change_mode); self.store.loadAllCookies()
        if not test: self.view.setHtml('<html><body style="background:#202020;color:white;font:18px sans-serif;padding:30px">ClipFlow</body></html>')

    def add_tab(self):
        view=QWebEngineView(self); view.setPage(Page(self,view)); self.tabs.addTab(view,self.service_name); self.tabs.setCurrentWidget(view)
        view.urlChanged.connect(self.address_changed)
        view.loadFinished.connect(lambda okay:self.status.setText(self.tr.text('auth_page_ready' if okay else 'auth_page_failed')))
        return view

    def address_changed(self,url):
        self.address.setText('https://'+url.host()+url.path() if url.scheme()=='https' else '')
    def apply_mode(self): self.profile.setHttpUserAgent(USER_AGENTS[self.mode.currentData()] or self.native_agent)

    def change_mode(self):
        self.apply_mode()
        try: self.settings_file.write_text(json.dumps({'mode':self.mode.currentData()},ensure_ascii=False),encoding='utf-8')
        except OSError: self.status.setText(self.tr.text('error.auth_storage_failed'))

    def login(self):
        url=LOGIN_URL if self.service==Service.YOUTUBE else 'https://www.instagram.com/accounts/login/'
        self.tabs.currentWidget().setUrl(QUrl(url))

    def open_service(self): self.tabs.currentWidget().setUrl(QUrl('https://www.'+DOMAINS[self.service]+'/'))

    def cookie_added(self,cookie):
        if self._disposing or self._logged_out: return
        domain=cookie.domain().lstrip('.').lower(); expected=DOMAINS[self.service]
        if domain==expected or domain.endswith('.'+expected):
            self.cookies[(cookie.domain(),cookie.path(),bytes(cookie.name()))]=QNetworkCookie(cookie); self.save_timer.start(250)

    def cookie_removed(self,cookie):
        if self._disposing: return
        domain=cookie.domain().lstrip('.').lower(); expected=DOMAINS[self.service]
        if domain!=expected and not domain.endswith('.'+expected): return
        self.cookies.pop((cookie.domain(),cookie.path(),bytes(cookie.name())),None)
        if bytes(cookie.name()).decode(errors='replace') in AUTH_NAMES[self.service]: self.session.snapshot.unlink(missing_ok=True)
        self.save_timer.start(250)

    def session_cookies(self):
        result=[]
        for cookie in self.cookies.values():
            expiry=-1 if cookie.isSessionCookie() else cookie.expirationDate().toSecsSinceEpoch()
            if expiry>=0 and expiry<=time.time(): continue
            result.append(dict(domain=cookie.domain(),path=cookie.path(),name=bytes(cookie.name()).decode(),value=bytes(cookie.value()).decode(),
                secure=cookie.isSecure(),httpOnly=cookie.isHttpOnly(),expires=expiry))
        return result

    def write_session(self):
        if self._disposing or self._logged_out: return False
        try: return self.session.save(self.session_cookies())
        except Exception:
            self.status.setText(self.tr.text('error.auth_storage_failed')); return False

    def save_session(self): self.status.setText(self.tr.text('session_saved' if self.write_session() else 'auth_session_missing'))

    def logout(self):
        self._logged_out=True; self.save_timer.stop(); self.cookies.clear(); self.store.deleteAllCookies(); self.profile.clearHttpCache(); self.session.logout()
        self.status.setText(self.tr.text('not_signed_in')); self.close()

    def _markers(self):
        if (self.directory/'logout-request').exists(): self.logout()
        elif self.close_path is not None and self.close_path.exists(): self.close()

    def closeEvent(self,event):
        self.save_timer.stop(); self.marker_timer.stop(); self.write_session(); super().closeEvent(event)

    def dispose(self):
        if self._disposing: return
        self._disposing=True; self.save_timer.stop(); self.marker_timer.stop()
        self.store.cookieAdded.disconnect(self.cookie_added); self.store.cookieRemoved.disconnect(self.cookie_removed)
        for index in range(self.tabs.count()):
            view=self.tabs.widget(index); view.stop(); view.page().deleteLater(); view.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        self.profile.deleteLater(); QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
