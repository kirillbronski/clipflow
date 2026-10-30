import os
import signal
import sys
from threading import Event

import pytest

from clipflow.domain.events import StageChanged
from clipflow.domain.models import JobState, Service
from clipflow.infrastructure.repository import SqliteJobRepository
from clipflow.providers.media import MediaPipeline
from tests.integration.test_media_pipeline import context, media_server, tools
from tests.ui.test_workbench import add, make_window


def test_restart_does_not_autostart(make_window, qtbot, tmp_path):
    window, provider = make_window()
    add(window, qtbot)
    path = window.presenter.repository.path
    window.close()
    qtbot.waitUntil(lambda: window.presenter.is_closed)
    repo = SqliteJobRepository(path)
    jobs = repo.recover()
    assert jobs[0].state == JobState.PAUSED
    restarted, provider = make_window(repository=repo)
    qtbot.wait(100)
    assert (
        not provider.started.is_set() and restarted.presenter.model.jobs[0].state == JobState.PAUSED
    )


def test_close_during_network_processing_or_auth(make_window, qtbot):
    window, provider = make_window()
    add(window, qtbot)
    window.presenter.start_queue()
    qtbot.waitUntil(provider.started.is_set)
    path = window.presenter.repository.path
    window.close()
    qtbot.waitUntil(lambda: window.presenter.is_closed, timeout=5000)
    assert provider.torn_down.is_set() and window.presenter.executor.is_idle
    repo = SqliteJobRepository(path)
    try:
        assert repo.recover()[0].state == JobState.PAUSED
    finally:
        repo.close()


def test_close_reaps_actual_ffmpeg(make_window, qtbot, tools, tmp_path, monkeypatch):
    import subprocess

    original = subprocess.Popen
    processes = []

    def record(*args, **kwargs):
        process = original(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(subprocess, 'Popen', record)

    class Processing:
        def __init__(self):
            self.started = Event()

        def execute(self, request, context):
            context.emit(StageChanged(JobState.PROCESSING))
            self.started.set()
            MediaPipeline._run(
                [
                    tools[0],
                    '-nostdin',
                    '-v',
                    'error',
                    '-re',
                    '-f',
                    'lavfi',
                    '-i',
                    'color=c=blue:s=16x16:r=1',
                    '-t',
                    '600',
                    '-f',
                    'null',
                    '-',
                ],
                context,
            )

    provider = Processing()
    window, _ = make_window(provider)
    add(window, qtbot)
    window.presenter.start_queue()
    qtbot.waitUntil(provider.started.is_set)
    qtbot.wait(250)
    window.close()
    qtbot.waitUntil(lambda: window.presenter.is_closed, timeout=5000)
    assert window.presenter.executor.is_idle
    assert processes and all(p.poll() is not None for p in processes)


def test_close_interrupts_ytdlp_internal_postprocessor(
    make_window, qtbot, media_server, tools, tmp_path, monkeypatch
):
    import subprocess

    from yt_dlp.postprocessor.ffmpeg import FFmpegPostProcessor

    from clipflow.providers.access import open_downloader

    processes = []
    spawned = Event()
    original = subprocess.Popen.__init__

    def record(process, *args, **kwargs):
        original(process, *args, **kwargs)
        processes.append(process)
        spawned.set()

    monkeypatch.setattr(subprocess.Popen, '__init__', record)

    class LongProcessing(FFmpegPostProcessor):
        def run(self, info):
            self.real_run_ffmpeg(
                [(str(media_server[1] / 'sample.mp4'), ['-stream_loop', '-1', '-re'])],
                [(str(tmp_path / 'long.mp4'), ['-t', '600', '-c', 'copy'])],
            )
            return [], info

    class Provider:
        def execute(self, request, context):
            with open_downloader(
                {'quiet': True, 'ffmpeg_location': tools[0]}, context=context
            ) as ydl:
                ydl.run_pp(LongProcessing(ydl), {})

    window, _ = make_window(Provider())
    add(window, qtbot)
    window.presenter.start_queue()
    try:
        qtbot.waitUntil(spawned.is_set, timeout=3000)
        qtbot.wait(200)
        window.close()
        qtbot.waitUntil(lambda: window.presenter.is_closed, timeout=4000)
        assert processes and all(p.poll() is not None for p in processes)
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.wait(3)
        window.presenter.shutdown()
        qtbot.waitUntil(lambda: window.presenter.is_closed, timeout=5000)


@pytest.mark.skipif(os.name != 'nt', reason='Windows executable shim regression')
def test_close_reaps_wrapper_and_child_holding_stderr(make_window, qtbot, tmp_path):
    import ctypes

    script = tmp_path / 'shim.py'
    pid_file = tmp_path / 'child.pid'
    script.write_text(
        'import subprocess,sys\nfrom pathlib import Path\n'
        'p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(600)"])\n'
        'Path(sys.argv[1]).write_text(str(p.pid))\np.wait()\n',
        encoding='utf-8',
    )

    class Provider:
        def execute(self, request, context):
            MediaPipeline._run(
                [sys.executable, str(script), str(pid_file)], context, capture_error=True
            )

    window, _ = make_window(Provider())
    add(window, qtbot)
    window.presenter.start_queue()
    qtbot.waitUntil(pid_file.exists, timeout=3000)
    child_pid = int(pid_file.read_text())
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(0x00100000, False, child_pid)
    assert handle
    try:
        window.close()
        qtbot.waitUntil(lambda: window.presenter.is_closed, timeout=5000)
        assert kernel.WaitForSingleObject(handle, 0) == 0
    finally:
        if kernel.WaitForSingleObject(handle, 0) != 0:
            os.kill(child_pid, signal.SIGTERM)
        kernel.CloseHandle(handle)
        window.presenter.shutdown()
        qtbot.waitUntil(lambda: window.presenter.is_closed, timeout=5000)


def test_ytdlp_real_merger_still_combines_separate_tracks(media_server, tools, tmp_path, context):
    import shutil

    from yt_dlp.postprocessor.ffmpeg import FFmpegMergerPP

    from clipflow.providers.access import open_downloader
    from tests.integration.test_media_pipeline import probe

    video = tmp_path / 'video.mp4'
    audio = tmp_path / 'audio.m4a'
    target = tmp_path / 'merged.mp4'
    shutil.copy2(media_server[1] / 'video-only.mp4', video)
    shutil.copy2(media_server[1] / 'audio.m4a', audio)
    formats = [
        {'acodec': 'none', 'vcodec': 'h264', 'protocol': 'http'},
        {'acodec': 'aac', 'vcodec': 'none', 'protocol': 'http'},
    ]
    with open_downloader({'quiet': True, 'ffmpeg_location': tools[0]}, context=context[0]) as ydl:
        result = ydl.run_pp(
            FFmpegMergerPP(ydl),
            {
                'filepath': str(target),
                'requested_formats': formats,
                '__files_to_merge': [str(video), str(audio)],
            },
        )
    assert result['filepath'] == str(target) and not video.exists() and not audio.exists()
    assert {s['codec_type'] for s in probe(target, tools)['streams']} == {'video', 'audio'}


def test_close_during_stalled_network_is_bounded(make_window, qtbot):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    from clipflow.providers.access import open_downloader

    class Stalled(BaseHTTPRequestHandler):
        entered = Event()
        released = Event()

        def log_message(self, *args):
            pass

        def do_GET(self):
            self.entered.set()
            self.released.wait(20)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Stalled)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    class Network:
        def execute(self, request, context):
            with (
                open_downloader({'quiet': True}, context=context) as ydl,
                ydl.urlopen(f'http://127.0.0.1:{server.server_port}/stall') as response,
            ):
                response.read()

    try:
        window, _ = make_window(Network())
        add(window, qtbot)
        window.presenter.start_queue()
        qtbot.waitUntil(Stalled.entered.is_set, timeout=2000)
        window.close()
        qtbot.waitUntil(lambda: window.presenter.is_closed, timeout=8000)
        assert window.presenter.executor.is_idle
    finally:
        Stalled.released.set()
        server.shutdown()
        server.server_close()
        thread.join(2)


def test_close_waits_for_and_reaps_auth_process(make_window, qtbot, tmp_path):
    import os
    import subprocess
    import sys

    from clipflow.infrastructure.auth import AuthProcessHandle, NativeAuthGateway

    gateway = NativeAuthGateway(tmp_path / 'auth')
    directory = tmp_path / 'auth' / 'YouTubeAuth'
    directory.mkdir(parents=True)
    process = subprocess.Popen(
        [sys.executable, '-c', 'import time; time.sleep(600)'],
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
    )
    handle = AuthProcessHandle(gateway, Service.YOUTUBE, process, directory, 'a' * 32)
    gateway._handles[Service.YOUTUBE] = handle
    try:
        window, _ = make_window()
        window.presenter.auth_gateway = gateway
        window.close()
        assert not window.presenter.is_closed
        qtbot.waitUntil(lambda: window.presenter.is_closed, timeout=7000)
        assert process.poll() is not None and not handle.close_path.exists()
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(3)


def test_recovery_after_file_written_before_db_commit(
    make_window, qtbot, media_server, tools, tmp_path
):
    from clipflow.providers.youtube import YouTubeProvider

    class Local(YouTubeProvider):
        def _extract(self, request, context):
            return {
                'id': 'ABC',
                'title': 'Crash recovery',
                'url': media_server[0] + '/sample.mp4',
                'ext': 'mp4',
            }

    window, _ = make_window(Local(MediaPipeline()))
    identity = add(window, qtbot)
    repo = window.presenter.repository
    original = repo.update

    def interrupted(job):
        if job.result_files:
            raise OSError('simulated database write failure')
        original(job)

    repo.update = interrupted
    window.presenter.start_queue()
    qtbot.waitUntil(lambda: window.presenter.executor.is_idle, timeout=15000)
    files = tuple((tmp_path / 'downloads').glob('YouTube/Crash recovery*.mp4'))
    assert len(files) == 1 and files[0].stat().st_size > 0
    before = files[0].stat().st_mtime_ns
    path = repo.path
    repo.update = original
    window.close()
    qtbot.waitUntil(lambda: window.presenter.is_closed)
    restored = SqliteJobRepository(path)
    restored.recover()
    restarted, _ = make_window(Local(MediaPipeline()), repository=restored)
    restarted.presenter.toggle_job(identity)
    qtbot.waitUntil(lambda: restored.get(identity).state == JobState.COMPLETED, timeout=15000)
    assert restored.get(identity).result_files == files and files[0].stat().st_mtime_ns == before
