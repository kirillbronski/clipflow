"""Headless checks of the real worker and caption writer; no Instagram login needed."""
import ast
import json
import queue
import sys
import threading
import time
import unittest
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'source'), str(ROOT / 'source/_internal')]
import yt_dlp
from platform_support import binary_path
from yt_dlp.extractor.getcourseru import GetCourseRuPlayerIE
from instagram_media import ClipFlowInstagramIE, download_photo, is_instagram_url, media_title, save_description
from media_names import short_media_title

# Compile application methods without initializing its Windows-only GUI dependencies.
tree = ast.parse((ROOT / 'source/downloader.py').read_text(encoding='utf-8-sig'))
app = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'App')
names = {'completed_media_paths', 'clean_download_sidecars', 'download_options'}
selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
selected += [node for node in app.body if isinstance(node, ast.FunctionDef) and node.name in {'worker', 'save_settings'}]
BASE = ROOT / 'assets'
QUALITY = {'Лучшее доступное': None}
access_error_message = lambda error, access: str(error)
exec(compile(ast.Module(body=selected, type_ignores=[]), str(ROOT / 'source/downloader.py'), 'exec'))

CAPTION = 'Полное описание 🎬\n\n' + 'Длинный текст ' * 60 + '\n#рилс #пост'
class FakeDL:
    description = CAPTION
    carousel = False
    fail = False
    def __init__(self, options): self.params = options
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def add_info_extractor(self, *args): pass
    def extract_info(self, *args, **kwargs):
        info = {'id': 'reel', 'channel': 'Автор', 'description': self.description, 'ext': 'webm'}
        if self.carousel:
            return {'_type': 'playlist', 'entries': [info, dict(info, id='photo', ext='jpg', url='https://cdn.example/photo.jpg', _clipflow_photo=True)]}
        return info
    def prepare_filename(self, info):
        template = self.params['outtmpl']
        prefix = template.split(' - ')[0] + ' - ' if ' - ' in template else ''
        return str(Path(self.params['paths']['home']) / (prefix + info['title'] + '.' + info['ext']))
    def process_ie_result(self, info, download=True):
        if self.fail: raise OSError('simulated interrupted download')
        # Simulate the final filename changing after MP4 merge / MP3 conversion.
        info['ext'] = 'mp3' if self.params.get('postprocessors') else 'mp4'
        path = Path(self.prepare_filename(info)); path.write_bytes(b'media')
        info['filepath'] = str(path)
        return info
    def urlopen(self, request):
        response = BytesIO(b'photo'); response.headers = {'Content-Length': '5'}
        return response

class DescriptionTests(unittest.TestCase):
    def run_worker(self, folder, enabled=False, mode='Видео — MP4', file_format='TXT'):
        state = SimpleNamespace(active_run=None, events=queue.Queue(), cancel=threading.Event(), skip_current=threading.Event())
        with patch.object(yt_dlp, 'YoutubeDL', FakeDL):
            worker(state, 'https://instagram.com/reel/Abc/', str(folder), mode, 'Лучшее доступное', lesson_scope='Всё', save_description_text=enabled, description_format=file_format)
        return [event[:2] for event in state.events.queue]

    def test_toggle_and_final_filename(self):
        for enabled in (False, True):
            for file_format in ('TXT', 'MD'):
                for mode, ext in [('Видео — MP4', 'mp4'), ('Только звук — MP3', 'mp3')]:
                    with self.subTest(enabled=enabled, mode=mode, file_format=file_format), TemporaryDirectory() as temp:
                        events = self.run_worker(temp, enabled, mode, file_format)
                        self.assertEqual(events[-1][0], 'done', events)
                        media = next(Path(temp).glob('*.' + ext))
                        text = media.with_suffix('.' + file_format.lower())
                        self.assertEqual(text.exists(), enabled)
                        paths = next(value[1] for kind, value in events if kind == 'files')
                        self.assertEqual(str(text.resolve()) in paths, enabled)
                        if enabled:
                            self.assertEqual(text.read_text(encoding='utf-8-sig'), CAPTION)
                            if file_format == 'MD': self.assertFalse(text.read_bytes().startswith(b'\xef\xbb\xbf'))
                        other = '.txt' if file_format == 'MD' else '.md'
                        self.assertFalse(media.with_suffix(other).exists())

    def test_missing_description(self):
        for caption in (None, '', ' \n '):
            with patch.object(FakeDL, 'description', caption), TemporaryDirectory() as temp:
                events = self.run_worker(temp, True)
                self.assertEqual(events[-1][0], 'done', events)
                self.assertFalse(list(Path(temp).glob('*.txt')))

    def test_carousel(self):
        with patch.object(FakeDL, 'carousel', True), TemporaryDirectory() as temp:
            events = self.run_worker(temp, True)
            self.assertEqual(events[-1][0], 'done', events)
            texts = list(Path(temp).glob('*.txt'))
            self.assertEqual(len(texts), 2)
            self.assertEqual({p.name[:3] for p in texts}, {'001', '002'})
            for path in texts: self.assertEqual(path.read_text(encoding='utf-8-sig'), CAPTION)

    def test_failed_download(self):
        with patch.object(FakeDL, 'fail', True), TemporaryDirectory() as temp:
            events = self.run_worker(temp, True)
            self.assertTrue(any(kind == 'summary' for kind, value in events), events)
            self.assertFalse(list(Path(temp).glob('*.txt')))

    def test_containment_and_atomic_failure(self):
        with TemporaryDirectory() as temp, TemporaryDirectory() as outside:
            media = Path(temp) / 'reel.mp4'; media.write_bytes(b'media')
            external = Path(outside) / 'reel.mp4'; external.write_bytes(b'media')
            self.assertEqual(save_description({'description': CAPTION}, [external], temp), [])
            target = media.with_suffix('.txt'); target.write_text('old caption')
            with patch('os.replace', side_effect=OSError('disk failure')):
                with self.assertRaises(OSError): save_description({'description': CAPTION}, [media], temp)
            self.assertEqual(target.read_text(), 'old caption')
            self.assertFalse(list(Path(temp).glob('*.tmp')))

    def test_settings_persist(self):
        global CONFIG
        with TemporaryDirectory() as temp:
            CONFIG = Path(temp) / 'settings.json'
            state = SimpleNamespace(folder_history=[], language='ru', installation_language='', detailed_list=False, interface_scale='100%')
            for name, value in [('folder', temp), ('quality', 'Лучшее доступное'), ('auto_download', True), ('save_instagram_description', True), ('instagram_description_format', 'MD')]:
                setattr(state, name, SimpleNamespace(get=lambda value=value: value))
            save_settings(state)
            settings = json.loads(CONFIG.read_text(encoding='utf-8'))
            self.assertTrue(settings['save_instagram_description'])
            self.assertEqual(settings['instagram_description_format'], 'MD')

if __name__ == '__main__': unittest.main()
