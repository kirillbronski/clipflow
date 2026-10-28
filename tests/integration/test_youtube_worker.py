"""Actual provider → media pipeline → local HTTP/FFmpeg, no live platform claims."""
import copy
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import shutil
import subprocess
from threading import Thread

import pytest
from yt_dlp import YoutubeDL

from clipflow.domain.events import CancellationToken, FilesSaved, RequestsDiscovered, StageChanged
from clipflow.domain.models import DownloadOptions, DownloadRequest, JobState
from clipflow.domain.urls import parse_url
from clipflow.providers.base import ExecutionContext
from clipflow.providers.media import MediaPipeline
from clipflow.providers.youtube import YouTubeProvider


class Auth:
    def options_for(self, profile, url):
        return {'http_headers': {'X-Test-Session':'synthetic-session'}}


@pytest.fixture(scope='module')
def server(tmp_path_factory):
    root = tmp_path_factory.mktemp('youtube-http')
    ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    assert ffmpeg and ffprobe
    subprocess.run([ffmpeg, '-v','error','-f','lavfi','-i','color=c=blue:s=96x64:r=10',
                    '-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','0.4',
                    '-c:v','libx264','-c:a','aac','-y',str(root/'source.mp4')],check=True)
    class Handler(SimpleHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_GET(self):
            if self.headers.get('X-Test-Session') != 'synthetic-session':
                self.send_error(403)
                return
            super().do_GET()
    http = ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=str(root)))
    thread = Thread(target=http.serve_forever,daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{http.server_port}/source.mp4',ffprobe
    http.shutdown();http.server_close();thread.join(timeout=3)


def metadata(url, identity):
    return {'_type':'video','id':identity,'title':'Название ролика','url':url,'ext':'mp4',
            'vcodec':'h264','acodec':'aac','width':96,'height':64,
            'webpage_url':f'https://www.youtube.com/watch?v={identity}'}


@pytest.mark.parametrize('fmt', ['mp4','mp3'])
def test_real_single_video_or_music_track(tmp_path, monkeypatch, server, fmt):
    url, ffprobe = server
    info = metadata(url,'track_A')
    def extract(self, page, download=False):
        return copy.deepcopy(info)
    monkeypatch.setattr(YoutubeDL,'extract_info',extract)
    events=[]
    ctx=ExecutionContext(CancellationToken(),events.append,Auth())
    host='music.youtube.com' if fmt=='mp3' else 'www.youtube.com'
    req=DownloadRequest(parse_url(f'https://{host}/watch?v=track_A'),DownloadOptions(tmp_path,format=fmt,auth_profile='youtube'))
    result=YouTubeProvider(MediaPipeline()).execute(req,ctx)
    assert [p.name for p in result.files] == ['Название ролика.'+fmt]
    data=json.loads(subprocess.check_output([ffprobe,'-v','error','-show_streams','-of','json',str(result.files[0])]))
    assert {s['codec_type'] for s in data['streams']} == ({'audio'} if fmt=='mp3' else {'video','audio'})
    states=[e.state for e in events if isinstance(e,StageChanged)]
    assert states == [JobState.PROBING,JobState.DOWNLOADING,JobState.PROCESSING]
    assert isinstance(events[-1],FilesSaved)
    assert 'synthetic-session' not in repr(result)+repr(events)


def test_playlist_children_save_with_original_001_numbers(tmp_path, monkeypatch, server):
    url,_=server
    def extract(self,page,download=False):
        if 'playlist?' in page:
            return {'_type':'playlist','id':'PL_test','entries':[
                {'_type':'url','id':'one','url':'one','title':'Первый'},None,
                {'_type':'url','id':'three','url':'three','title':'Третий'}]}
        return metadata(url,parse_url(page).canonical_id)
    monkeypatch.setattr(YoutubeDL,'extract_info',extract)
    events=[]
    ctx=ExecutionContext(CancellationToken(),events.append,Auth())
    req=DownloadRequest(parse_url('https://music.youtube.com/playlist?list=PL_test'),DownloadOptions(tmp_path,format='mp3'))
    provider=YouTubeProvider(MediaPipeline())
    parent=provider.execute(req,ctx)
    assert parent.files == () and parent.discovered_count == 2
    children=[r for e in events if isinstance(e,RequestsDiscovered) for r in e.requests]
    results=[provider.execute(r,ctx) for r in children]
    assert [r.files[0].name for r in results] == ['001 - Название ролика.mp3','003 - Название ролика.mp3']
    for r in results:
        modified=r.files[0].stat().st_mtime_ns
        child=children[results.index(r)]
        assert provider.execute(child,ctx).files == r.files
        assert r.files[0].stat().st_mtime_ns == modified
