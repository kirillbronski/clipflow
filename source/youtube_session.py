"""Protected YouTube session shared with ClipFlow's embedded Qt sign-in window."""
import http.cookiejar
import json
import os
from pathlib import Path
import subprocess
import sys
import time

class YouTubeSession:
    domain = 'youtube.com'
    login_flag = '--youtube-login'
    service = 'YouTube'
    def __init__(self, directory, protect):
        self.directory=Path(directory).resolve()
        self.snapshot=self.directory/'session.dat'
        self.protect=protect
        self.process=None
    def restore_profile(self):
        self.directory.mkdir(parents=True,exist_ok=True)
    @staticmethod
    def authenticated(cookies):
        return any(item.get('name') in ('SAPISID','__Secure-3PAPISID','__Secure-1PAPISID')
                   and item.get('value') and (item.get('expires',-1)<0 or item['expires']>time.time())
                   for item in cookies)
    def saved(self):
        if (self.directory/'logout-request').exists():return []
        try:
            cookies=json.loads(self.protect(self.snapshot.read_bytes(),decrypt=True))
            cookies=[item for item in cookies if item.get('domain','').lstrip('.').lower()==self.domain
                     or item.get('domain','').lower().endswith('.'+self.domain)]
            return cookies if self.authenticated(cookies) else []
        except (OSError,ValueError):return []
    def cookies(self):
        cookies=self.saved()
        if not cookies:
            raise RuntimeError(f'Сессия {self.service} недоступна. Войдите во встроенном окне.')
        return cookies
    def capture(self):return self.cookies()
    def launch(self,language='ru'):
        if self.process is not None and self.process.poll() is None:return self.process
        arguments=([sys.executable,self.login_flag] if getattr(sys,'frozen',False)
                   else [sys.executable,str(Path(__file__).with_name('embedded_auth.py'))])
        if not getattr(sys,'frozen',False):arguments.append(self.login_flag)
        arguments.extend(['--language',language])
        self.process=subprocess.Popen(arguments,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        return self.process
    def apply(self,jar):
        for item in self.cookies():
            expiry=item.get('expires',-1);domain=item['domain']
            jar.set_cookie(http.cookiejar.Cookie(0,item['name'],item['value'],None,False,
                domain,domain.startswith('.'),domain.startswith('.'),item.get('path','/'),True,
                item.get('secure',False),int(expiry) if expiry>0 else None,expiry<=0,
                None,None,{'HttpOnly':item.get('httpOnly',False)},False))
    def logout(self):
        self.directory.mkdir(parents=True,exist_ok=True)
        (self.directory/'logout-request').write_text('sign out')
        self.snapshot.unlink(missing_ok=True)
