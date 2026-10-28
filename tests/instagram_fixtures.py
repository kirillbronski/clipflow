"""Synthetic Instagram products and explicit offline pacing-policy doubles."""
from datetime import datetime, timezone
from urllib.parse import urlparse
from contextlib import contextmanager

import pytest
from yt_dlp import YoutubeDL

from clipflow.domain.events import CancellationToken
from clipflow.domain.models import DownloadOptions, DownloadRequest
from clipflow.domain.urls import parse_url
from clipflow.providers.base import ExecutionContext


class Gate:
    def __init__(self): self.calls=[]
    def acquire(self,kind,cancel):
        cancel.raise_if_cancelled()
        self.calls.append(kind)
    def record_completed_post(self): self.calls.append('completed')
    @contextmanager
    def request(self,kind,cancel):
        self.acquire(kind,cancel)
        yield lambda:True
    def record_429(self,retry_after):
        from clipflow.domain.events import RateLimitDeferred
        return RateLimitDeferred(datetime(2030,1,1,tzinfo=timezone.utc),False)


class Auth:
    def options_for(self,profile,url): return {}


def context():
    events=[]
    gate=Gate()
    return ExecutionContext(CancellationToken(),events.append,Auth(),gate),events,gate


def request(folder,url='https://instagram.com/p/ABC/',**options):
    return DownloadRequest(parse_url(url),DownloadOptions(folder,**options))


def photo(pk='101',url='https://cdn.example.test/image.png'):
    return {'pk':pk,'media_type':1,'image_versions2':{'candidates':[
        {'url':'https://cdn.example.test/small.jpg','width':8,'height':8},
        {'url':url,'width':1000,'height':1000}]}}


def video(pk='102',url='https://cdn.example.test/video.mp4'):
    return {'pk':pk,'media_type':2,'video_codec':'h264','has_audio':True,
            'video_versions':[{'id':'best','url':url,'width':96,'height':64}]}


def product(base=None):
    return {'pk':'100','user':{'username':'alice','pk':'123','full_name':'Display Name'},
            'caption':{'text':'Подпись — полностью\nВторая строка'},
            'taken_at':int(datetime(2026,10,28,tzinfo=timezone.utc).timestamp()),
            'carousel_media':[photo(url=base+'/image.png') if base else photo(),
                              video(url=base+'/video.mp4') if base else video(),
                              photo('103',base+'/image.png') if base else photo('103')]}


def isolate_instagram(monkeypatch):
    from clipflow.providers.instagram_post import InstagramExtractor
    # Real initialization fetches Instagram's homepage before _real_extract.
    monkeypatch.setattr(InstagramExtractor,'_real_initialize',lambda self:None)
    original=YoutubeDL.urlopen
    def local_only(self,request):
        url=request if isinstance(request,str) else request.url
        if urlparse(url).hostname not in {'127.0.0.1','localhost'}:
            pytest.fail('Instagram tests attempted a non-loopback network request')
        return original(self,request)
    monkeypatch.setattr(YoutubeDL,'urlopen',local_only)
