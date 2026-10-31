"""New tests use temporary profiles; legacy scripts run in separate processes."""

import shutil
import subprocess
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import ClassVar

import pytest
from PySide6.QtCore import QMimeData

from clipflow.application.scheduler import Scheduler
from clipflow.application.submission import SubmissionService
from clipflow.domain.models import (
    ContentKind,
    DownloadOptions,
    Service,
)
from clipflow.infrastructure.executor import ThreadExecutor
from clipflow.infrastructure.repository import SqliteJobRepository
from clipflow.infrastructure.settings import AppSettings
from clipflow.ui.presenter import WorkbenchPresenter
from clipflow.ui.window import MainWindow
from tests.instagram_fixtures import Auth
from tests.support.workbench import HeldProvider


@pytest.fixture(autouse=True)
def isolated_profile(tmp_path, monkeypatch):
    monkeypatch.setenv('CLIPFLOW_DATA_DIR', str(tmp_path / 'profile'))


@pytest.fixture
def make_window(qtbot, tmp_path):
    windows = []

    def make(provider=None, repository=None, settings=None):
        provider = provider or HeldProvider()
        repository = repository or SqliteJobRepository(tmp_path / f'queue-{len(windows)}.sqlite3')
        presets = {s: DownloadOptions(tmp_path / 'downloads') for s in Service}
        settings = settings or AppSettings(presets=presets)
        executor = ThreadExecutor({(Service.YOUTUBE, ContentKind.VIDEO): provider}, Auth())
        scheduler = Scheduler(repository, executor)
        presenter = WorkbenchPresenter(
            SubmissionService(repository), scheduler, settings, repository
        )
        # This fixture owns teardown: pytest-qt deletes registered widgets even
        # when closeEvent correctly waits for an asynchronous worker.
        window = MainWindow(presenter)
        window.show()
        windows.append(window)
        return window, provider

    yield make
    for window in windows:
        window.presenter.shutdown()
        qtbot.waitUntil(lambda w=window: w.presenter.is_closed, timeout=5000)
        window.close()
        window.deleteLater()


@pytest.fixture(scope='module')
def tools():
    ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    assert ffmpeg, 'Native FFmpeg is required for T4 acceptance'
    assert ffprobe, 'Native FFprobe is required for T4 acceptance'
    return ffmpeg, ffprobe


@pytest.fixture(scope='module')
def media_server(tmp_path_factory, tools):
    root = tmp_path_factory.mktemp('media-http')
    source = root / 'sample.mp4'
    subprocess.run(
        [
            tools[0],
            '-v',
            'error',
            '-f',
            'lavfi',
            '-i',
            'color=c=blue:s=96x64:r=10',
            '-f',
            'lavfi',
            '-i',
            'sine=frequency=440:sample_rate=48000',
            '-t',
            '0.4',
            '-c:v',
            'libx264',
            '-c:a',
            'aac',
            '-y',
            str(source),
        ],
        check=True,
    )
    compatible = root / 'compatible.webm'
    subprocess.run(
        [
            tools[0],
            '-v',
            'error',
            '-i',
            str(source),
            '-c:v',
            'libvpx-vp9',
            '-c:a',
            'libopus',
            '-y',
            str(compatible),
        ],
        check=True,
    )
    subprocess.run(
        [
            tools[0],
            '-v',
            'error',
            '-i',
            str(source),
            '-an',
            '-c:v',
            'copy',
            '-y',
            str(root / 'video-only.mp4'),
        ],
        check=True,
    )
    subprocess.run(
        [
            tools[0],
            '-v',
            'error',
            '-i',
            str(source),
            '-vn',
            '-c:a',
            'copy',
            '-y',
            str(root / 'audio.m4a'),
        ],
        check=True,
    )
    # A real tiny PNG; larger payload lets the cancellation test leave a partial.
    subprocess.run(
        [
            tools[0],
            '-v',
            'error',
            '-f',
            'lavfi',
            '-i',
            'color=c=red:s=8x8',
            '-frames:v',
            '1',
            '-y',
            str(root / 'photo.png'),
        ],
        check=True,
    )
    (root / 'large.jpg').write_bytes(b'photo-byte-stream' * 20000)
    (root / 'empty.jpg').write_bytes(b'')

    class Handler(SimpleHTTPRequestHandler):
        hits = 0
        ranges: ClassVar[list] = []  # shared by every request of the server
        paths: ClassVar[list] = []

        def log_message(self, *args):
            pass

        def do_GET(self):
            type(self).hits += 1
            type(self).paths.append(self.path)
            if self.path == '/protected.png':
                if self.headers.get('Referer') != 'https://www.instagram.com/':
                    self.send_error(403)
                    return
                self.path = '/photo.png'
            if self.path == '/resume.jpg':
                data = (root / 'large.jpg').read_bytes()
                range_header = self.headers.get('Range')
                type(self).ranges.append(range_header)
                start = int(range_header[6:-1]) if range_header else 0
                if start >= len(data):
                    self.send_response(416)
                    self.send_header('Content-Range', f'bytes */{len(data)}')
                    self.end_headers()
                    return
                self.send_response(206 if start else 200)
                self.send_header('Content-Length', str(len(data) - start))
                self.send_header('Content-Range', f'bytes {start}-{len(data) - 1}/{len(data)}')
                self.end_headers()
                self.wfile.write(data[start:])
                return
            super().do_GET()

    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(root)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_port}', root, Handler
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


@pytest.fixture
def clipboard(qapp):
    clipboard = qapp.clipboard()
    original = QMimeData()
    current = clipboard.mimeData()
    if current:
        for fmt in current.formats():
            original.setData(fmt, current.data(fmt))
    yield clipboard
    if original.formats():
        clipboard.setMimeData(original)
    else:
        clipboard.clear()  # Restore an empty clipboard, not an owned empty MIME object.
