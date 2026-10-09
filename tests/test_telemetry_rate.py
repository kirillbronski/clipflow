"""Fragment bursts, including inaccurate 100% estimates, must not flood the UI."""
import sys, queue, threading
from types import SimpleNamespace
from unittest.mock import patch
sys.path[:0] = ['source', 'source/_internal']
import clipflow as downloader

clock = [0.0]
class FakeDownloader:
    def __init__(self, options): self.hook = options['progress_hooks'][0]
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def add_info_extractor(self, extractor): pass
    def extract_info(self, *args, **kwargs): return {'title': 'Public video'}
    def process_ie_result(self, info, **kwargs):
        for number in range(3000):
            clock[0] += .001
            self.hook({'status': 'downloading', 'filename': 'stream', 'info_dict': info,
                       'downloaded_bytes': 1000000 + number * 1000,
                       'total_bytes_estimate': 1, 'speed': 1000000000})
        self.hook({'status': 'finished'})
        return info
app = SimpleNamespace(events=queue.Queue(), active_run=object(), cancel=threading.Event(), skip_current=threading.Event())
with patch.object(downloader.yt_dlp, 'YoutubeDL', FakeDownloader), \
     patch.object(downloader, 'download_options', lambda folder, mode, quality, hook, access: {'progress_hooks': [hook]}), \
     patch.object(downloader.time, 'monotonic', lambda: clock[0]), \
     patch.object(downloader, 'clean_download_sidecars'), \
     patch.object(downloader, 'completed_media_paths', return_value=[]):
    downloader.App.worker(app, 'https://youtu.be/public', '/tmp', 'Видео — MP4', '1080p')
events = list(app.events.queue)
progress = [e[1] for e in events if e[0] == 'progress']
assert 5 <= len(progress) <= 7, len(progress)
assert all(p[2] < 2 for p in progress), progress
assert events[-1][0] == 'done', events[-1]
print('PASS: 3000 fragment callbacks in 3 seconds =>', len(progress), 'progress events; estimated 100% cannot bypass throttle; speed uses transferred bytes')
