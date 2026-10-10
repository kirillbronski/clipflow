"""Profile pagination policy, queue expansion, failures and cancellation without live login."""
import sys
import threading
import unittest
from pathlib import Path
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
sys.path[:0] = ['source', 'source/_internal']
from instagram_profile import profile_username, profile_posts
import instaloader
from yt_dlp.utils import DownloadError

class Loader:
    def __init__(self, **kwargs):
        self.context = SimpleNamespace(update_cookies=lambda _: None)
    def __enter__(self): return self
    def __exit__(self, *args): pass

class ProfileTests(unittest.TestCase):
    def test_urls(self):
        self.assertEqual(profile_username('https://instagram.com/test.user/?x=1'), 'test.user')
        for url in ['https://instagram.com/p/ABC/', 'https://instagram.com/accounts/', 'https://instagram.com/reels/', 'https://instagram.com.evil.com/test', 'https://user@instagram.com/test', 'https://instagram.com/../test']:
            self.assertIsNone(profile_username(url), url)

    def test_post_reel_dedup_limit_and_order(self):
        def post(code, day): return SimpleNamespace(shortcode=code, date_utc=datetime(2026, 10, day, tzinfo=timezone.utc))
        profile = SimpleNamespace(is_private=False, get_posts=lambda: iter([post('AAA', 1), post('BBB', 2)]), get_reels=lambda: iter([post('BBB', 2), post('CCC', 3)]))
        with patch.object(instaloader, 'Instaloader', Loader), patch.object(instaloader.Profile, 'from_username', return_value=profile):
            values = profile_posts('https://instagram.com/test/', 10, None, threading.Event())
            self.assertEqual(values, ['https://www.instagram.com/p/CCC/', 'https://www.instagram.com/p/BBB/', 'https://www.instagram.com/p/AAA/'])
            event = threading.Event();event.set()
            with self.assertRaises(DownloadError): profile_posts('https://instagram.com/test/', 10, None, event)
            profile.is_private = True;profile.followed_by_viewer = False;profile.is_self = False
            with self.assertRaisesRegex(DownloadError, 'Закрытый профиль'): profile_posts('https://instagram.com/test/', 10, None, threading.Event())

    def test_network_failure_is_not_empty_success(self):
        with patch.object(instaloader, 'Instaloader', Loader), patch.object(instaloader.Profile, 'from_username', side_effect=instaloader.exceptions.AbortDownloadException('429')):
            with self.assertRaisesRegex(DownloadError, 'Не удалось получить профиль'):
                profile_posts('https://instagram.com/test/', 0, None, threading.Event())

    def test_worker_profile_failure_and_cancellation(self):
        import clipflow, queue
        for cancelled in (False, True):
            state = SimpleNamespace(active_run=None, events=queue.Queue(), cancel=threading.Event(), skip_current=threading.Event())
            if cancelled: state.cancel.set()
            with patch.object(clipflow, 'profile_posts', side_effect=DownloadError('limit')):
                clipflow.App.worker(state, 'https://instagram.com/test/', '.', 'Видео — MP4', 'Лучшее доступное')
            kinds = [event[0] for event in state.events.queue]
            self.assertEqual(kinds[-1], 'cancelled' if cancelled else 'error')
            self.assertNotIn('done', kinds)
            self.assertNotIn('profile_posts', kinds)

    def test_gui_profile_queue_and_snapshot(self):
        import clipflow
        with __import__('tempfile').TemporaryDirectory() as temp:
            root = clipflow.ctk.CTk(); app = clipflow.App(root)
            app.auto_download.set(False)
            app.schedule_quality_check = lambda *_: None
            app.tabs.set('Instagram');app.activate_tab()
            app.folder.set(temp);app.url.set('https://instagram.com/test/')
            app.instagram_post_folder.set(False)
            app.instagram_profile_limit.set('До 50 публикаций')
            app.start(auto_start=False)
            profile_job = app.pending_jobs.pop()
            self.assertTrue(profile_job['post_folder'])
            self.assertEqual(profile_job['profile_limit'], 50)
            app.active_job = profile_job;app.active_run = object();app.busy = True
            app.launch_next = lambda: None
            urls = ['https://www.instagram.com/p/AAA/', 'https://www.instagram.com/p/BBB/']
            for _ in range(2):
                app.events.put(('profile_posts', urls, app.active_run));app._poll_updates()
            self.assertEqual(len(app.pending_jobs), 2)
            self.assertEqual([job['url'] for job in app.pending_jobs], urls)
            self.assertTrue(all(job['post_folder'] for job in app.pending_jobs))
            app.instagram_profile_limit.set('До 10 публикаций')
            self.assertEqual(app.pending_jobs[0]['profile_limit'], 50)
            root.destroy()

if __name__ == '__main__': unittest.main()
