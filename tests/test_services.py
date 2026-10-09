"""Exercise Windows 1.8.4 features with macOS storage and a deterministic probe."""
import sys, json, http.cookiejar, threading, tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path[:0] = ['source', 'source/_internal']
import clipflow as app
from instagram_media import ClipFlowInstagramIE, is_instagram_url, download_photo
from instagram_session import InstagramSession
from media_names import short_media_title

root = app.ctk.CTk(); window = app.App(root)
window.auto_download.set(False)
root.update()
window.schedule_quality_check = lambda *args: None
try:
    assert app.default_download_folder() == str(Path.home()/'Downloads/ClipFlow')
    assert short_media_title('A — B\n C ' * 20) == ('A - B C ' * 20)[:56].rstrip()
    assert app.supported_url('https://www.instagram.com/reel/abc/?igsh=xyz')
    assert not app.supported_url('https://instagram.com.evil.example/p/abc/')
    assert not app.supported_url('https://instagram.com/profile/')
    for service in ('YouTube', 'Instagram', 'GetCourse'):
        window.tabs.set(service); window.activate_tab(); root.update()
        assert window.contexts[service]['start_button'].winfo_ismapped(), (service, window.tabs.get(), window.tabs.tab(service).winfo_manager(), window.contexts[service]['start_button'].winfo_manager())
        assert window.contexts[service]['start_button'].cget('text') == ''
    window.tabs.set('Instagram'); window.activate_tab()
    assert window.mode.get() == 'Видео и фото'
    assert app.COLORS['primary_action'] == '#C13584'
    # Match the Windows design: sign-in remains available through Accounts.
    assert not window.instagram_auth_row.winfo_manager()
    window.language = 'en'; window.localize_ui()
    assert window.instagram_description_switch.cget('text') == 'Save description'
    assert window.instagram_scope_box._text_label.cget('text') == 'All media'
    for size in ('1080x780', '880x680'):
        root.geometry(size); root.update()
        for widget in (window.instagram_description_switch,window.instagram_description_format_box,window.start_button):
            assert widget.winfo_rootx() >= root.winfo_rootx()
            assert widget.winfo_rootx()+widget.winfo_width() <= root.winfo_rootx()+root.winfo_width(), (size,widget)
    window.language = 'ru'; window.localize_ui()
    calls=[]
    window.auto_download.set(True)
    with patch.object(window,'start',side_effect=lambda **kwargs:calls.append((window.tabs.get(),window.quality.get()))):
        for service in ('YouTube','Instagram','GetCourse'):
            context=window.contexts[service];context['quality_request']=77;context['quality_pending']=True
            context['quality'].set('720p')
            window.events.put(('quality_result',(service,77,[1080,720],None)))
            window._poll_updates()
            assert window.tabs.get()=='Instagram'
            assert context['quality_box']._i18n_values==['Лучшее доступное','1080p','720p']
        window.contexts['YouTube']['quality_request']=78
        window.events.put(('quality_result',('YouTube',77,[2160],None)));window._poll_updates()
        assert window.contexts['YouTube']['quality_box']._i18n_values==['Лучшее доступное','1080p','720p']
    assert calls==[(name,'Лучшее доступное') for name in ('YouTube','Instagram','GetCourse')]
    window.auto_download.set(False)
    # Exact metadata processing for the actual probe, with the network replaced.
    class Probe:
        def __init__(self,options):self.cookiejar=None
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def add_info_extractor(self,ie):pass
        def extract_info(self,*args,**kwargs):return {'formats':[{'height':1080,'vcodec':'h264'},{'height':720,'vcodec':'h264'},{'height':720,'vcodec':'h264'},{'vcodec':'none'}]}
    context=window.contexts['YouTube'];context['url'].set('https://youtu.be/test');context['quality_request']=100
    with patch.object(app.yt_dlp,'YoutubeDL',Probe):
        window.check_quality('YouTube',100)
        event=window.events.get(timeout=5)
        assert event==('quality_result',('YouTube',100,[1080,720],None)),event
    with tempfile.TemporaryDirectory() as temp:
        window.folder.set(temp);window.save_instagram_description.set(True);window.instagram_description_format.set('MD');window.save_settings()
        assert json.loads(app.CONFIG.read_text())['instagram_description_format']=='MD'
        second = app.App.__new__(app.App)  # Session isolation is independent of UI.
        from cryptography.fernet import Fernet
        cipher=Fernet(Fernet.generate_key())
        protect=lambda data,decrypt=False: cipher.decrypt(data) if decrypt else cipher.encrypt(data)
        session=InstagramSession(Path(temp)/'IG',protect);session.restore_profile()
        cookies=[{'domain':'.instagram.com','name':'sessionid','value':'fake','expires':-1,'path':'/'},{'domain':'.youtube.com','name':'SAPISID','value':'other','expires':-1}]
        session.snapshot.write_bytes(protect(json.dumps(cookies).encode()))
        jar=http.cookiejar.CookieJar();session.apply(jar)
        assert [cookie.domain for cookie in jar]==['.instagram.com']
        session.logout();assert not session.saved()
    extractor=ClipFlowInstagramIE()
    photo=extractor._extract_product_media({'pk':'123','image_versions2':{'candidates':[{'url':'https://cdn.example/small.jpg','width':100,'height':100},{'url':'https://cdn.example/large.jpg','width':1000,'height':1000}]}})
    assert photo['_clipflow_photo'] and photo['url'].endswith('large.jpg')
    video=extractor._extract_product_media({'pk':'456','video_versions':[{'url':'https://cdn.example/clip.mp4','width':1080,'height':1920}]})
    assert not video.get('_clipflow_photo') and video['formats']
    print('PASS 1.8.4: three-service UI, 880px layout, Instagram filters/descriptions/RU-EN, available quality, stale probes, best-quality auto-download, platform folders, short names and isolated sessions')
finally:
    root.destroy()
