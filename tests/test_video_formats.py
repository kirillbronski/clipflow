"""Exercise actual FFmpeg postprocessing of single-stream downloads in each container."""
import ast
import gc
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'source'))
import yt_dlp
from platform_support import binary_path
ROOT = Path(__file__).resolve().parents[1]
tree = ast.parse((ROOT / 'source/clipflow.py').read_text(encoding='utf-8-sig'))
selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'download_options']
QUALITY = {'Лучшее доступное': None, '720p': 720}
exec(compile(ast.Module(body=selected, type_ignores=[]), str(ROOT / 'source/clipflow.py'), 'exec'))

class VideoFormats(unittest.TestCase):
    def test_real_container_conversion_and_resume(self):
        ffmpeg, ffprobe = binary_path('ffmpeg'), binary_path('ffprobe')
        self.assertTrue(ffmpeg and ffprobe, 'FFmpeg and FFprobe required')
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'source.mp4'
            subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i',
                            'color=c=black:s=64x64:r=10', '-f', 'lavfi', '-i', 'sine=frequency=440',
                            '-t', '0.3', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(source)], check=True)
            for container in ('mp4', 'mkv', 'webm'):
                with self.subTest(container=container):
                    folder = root / container
                    options = download_options(str(folder), 'Видео — ' + ('WebM' if container == 'webm' else container.upper()), '720p', lambda _: None)
                    options.update(enable_file_urls=True)
                    for repeat in (False, True):
                        with yt_dlp.YoutubeDL(options) as dl:
                            result = dl.process_ie_result({'id': 'test', 'title': 'sample', 'url': source.as_uri(),
                                                          'extractor': 'generic', 'height': 64, 'width': 64, 'ext': 'mp4', 'vcodec': 'h264', 'acodec': 'aac'}, download=True)
                        final = folder / ('sample.' + container)
                        self.assertTrue(final.is_file(), result)
                        if repeat:
                            self.assertEqual(final.stat().st_mtime_ns, modified)
                        modified = final.stat().st_mtime_ns
                    gc.collect()  # Release urllib file handlers before Windows temporary-directory cleanup.
                    probe = json.loads(subprocess.check_output([ffprobe, '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(final)], text=True))
                    self.assertIn({'mp4': 'mp4', 'mkv': 'matroska', 'webm': 'webm'}[container], probe['format']['format_name'])
                    self.assertEqual({s['codec_type'] for s in probe['streams']}, {'video', 'audio'})
                    if container == 'webm':
                        self.assertEqual({s['codec_name'] for s in probe['streams']}, {'vp9', 'opus'})
                    self.assertEqual([p.name for p in folder.iterdir()], [final.name])

if __name__ == '__main__': unittest.main()
