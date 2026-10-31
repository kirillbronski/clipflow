"""Real Qt/HTTP/FFmpeg package acceptance, fenced to a fresh explicit test root."""

import argparse
import json
import os
import platform
import sys
from dataclasses import replace
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from clipflow.version import APP_VERSION

FIXTURE_ARGS = (
    '-v',
    'error',
    '-nostdin',
    '-f',
    'lavfi',
    '-i',
    'color=c=blue:s=96x64:r=10',
    '-f',
    'lavfi',
    '-i',
    'sine=frequency=440:sample_rate=48000',
    '-t',
    '0.3',
    '-c:v',
    'libx264',
    '-c:a',
    'aac',
    '-y',
)


def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ui-self-test', action='store_true')
    parser.add_argument('--data-dir', required=True)
    parser.add_argument('--report', required=True)
    parser.add_argument('--require-frozen', action='store_true')
    return parser


def _fenced_paths(args):
    """A fresh data root and the report path, both inside CLIPFLOW_DATA_DIR; else None."""
    if not os.environ.get('CLIPFLOW_DATA_DIR'):
        return None
    isolated = Path(os.environ['CLIPFLOW_DATA_DIR']).resolve()
    root = Path(args.data_dir).resolve()
    report = Path(args.report).resolve()
    if (
        not root.is_relative_to(isolated)
        or not report.is_relative_to(isolated)
        or report == root
        or (root.exists() and any(root.iterdir()))
    ):
        return None
    return root, report


def _bundled_tools(proof):
    from clipflow.ui.bootstrap import _binary

    tools = {name: _binary(name) for name in ('ffmpeg', 'ffprobe', 'node')}
    assert all(tools.values())
    if proof['frozen']:
        assert all(
            Path(p).resolve().is_relative_to(Path(sys._MEIPASS).resolve()) for p in tools.values()
        )
    proof['tools'] = {name: Path(value).name for name, value in tools.items()}
    return tools


def _serve(root, served):
    class LocalHandler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(LocalHandler, directory=str(root)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    served.append((server, thread))
    return server.server_port


def _local_provider(pipeline, port):
    from clipflow.providers.base import MediaItem

    class LocalProvider:
        def execute(self, request, execution):
            item = MediaItem(
                'local',
                1,
                'video',
                'ClipFlow local package test',
                {'id': 'local', 'ext': 'mp4', 'url': f'http://127.0.0.1:{port}/fixture.mp4'},
            )
            return pipeline.save(item, request, execution)

    return LocalProvider()


def _accept(app, window, pipeline, context, job, root, proof):
    """The finished job really holds playable media and the window renders at minimum size."""
    assert len(job.result_files) == 1 and job.result_files[0].is_file()
    probe = pipeline._probe(job.result_files[0], context)
    assert {'audio', 'video'} <= {s['codec_type'] for s in probe['streams']}
    assert APP_VERSION in window.windowTitle() and window.presenter.executor.is_idle
    assert not window.windowIcon().isNull()
    window.resize(880, 680)
    app.processEvents()
    assert window.queue_view.width() > 300
    window.grab().save(str(root / 'ui.png'))
    proof['local_transfer'] = True
    proof['files'] = [p.name for p in job.result_files]


def _run(app, window, root, proof, served):
    """Download a local fixture through the real queue; True when it completed and checked out."""
    from PySide6.QtCore import QTimer

    from clipflow.domain.events import CancellationToken
    from clipflow.domain.models import JobState, Service
    from clipflow.providers.base import ExecutionContext
    from clipflow.providers.media import MediaPipeline

    presenter = window.presenter
    tools = _bundled_tools(proof)
    pipeline = MediaPipeline(ffmpeg=tools['ffmpeg'], ffprobe=tools['ffprobe'], node=tools['node'])
    context = ExecutionContext(
        CancellationToken(), lambda event: None, presenter.auth_gateway, None
    )
    pipeline._run([tools['ffmpeg'], *FIXTURE_ARGS, str(root / 'fixture.mp4')], context)
    provider = _local_provider(pipeline, _serve(root, served))
    # No network-capable provider remains reachable, including quality probes.
    presenter.executor.registry = {key: provider for key in presenter.executor.registry}
    options = replace(presenter.settings.presets[Service.YOUTUBE], folder=root / 'downloads')
    assert presenter.update_preset(Service.YOUTUBE, options)
    outcomes = []

    def start():
        if presenter.submit('https://youtu.be/CLIPFLOW_SELF_TEST') is None:
            app.exit(1)
            return
        presenter.start_queue()

    def poll():
        try:
            jobs = presenter.repository.list()
            if not jobs or jobs[0].state not in {JobState.COMPLETED, JobState.FAILED}:
                return
            timer.stop()
            assert jobs[0].state == JobState.COMPLETED
            _accept(app, window, pipeline, context, jobs[0], root, proof)
        except Exception:  # noqa: BLE001  # подпроект 3
            timer.stop()
            app.exit(1)
            return
        outcomes.append(True)
        window.close()

    timer = QTimer(window)
    timer.setInterval(100)
    timer.timeout.connect(poll)
    window.show()
    timer.start()
    QTimer.singleShot(0, start)
    QTimer.singleShot(30000, lambda: app.exit(2))
    return app.exec() == 0 and bool(outcomes)


def _finish(window, served, proof, report):
    presenter = window.presenter
    presenter.shutdown()
    presenter.executor.drain()
    presenter.auth_gateway.drain()
    presenter._finish_shutdown()
    window.dispose_ui()
    for server, thread in served:
        server.shutdown()
        server.server_close()
        thread.join(3)
    proof['worker_idle'] = presenter.executor.is_idle
    proof['legacy_modules'] = [
        name for name in ('tkinter', '_tkinter', 'customtkinter') if name in sys.modules
    ]
    proof['passed'] = proof['passed'] and proof['worker_idle'] and not proof['legacy_modules']
    report.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main(argv=None):
    args = _parser().parse_args(argv)
    paths = _fenced_paths(args)
    if paths is None:
        return 2
    root, report = paths
    root.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    proof = {
        'passed': False,
        'version': APP_VERSION,
        'ui': 'qt',
        'frozen': bool(getattr(sys, 'frozen', False)),
        'os': platform.platform(),
        'cpu': platform.machine(),
        'local_transfer': False,
    }
    if args.require_frozen and not proof['frozen']:
        return 2
    from clipflow.ui.bootstrap import create_application

    app, window = create_application([], root)
    served = []
    try:
        proof['passed'] = _run(app, window, root, proof, served)
    except Exception:  # noqa: BLE001  # подпроект 3
        proof['error'] = 'package_ui_self_test_failed'
    finally:
        _finish(window, served, proof, report)
    return 0 if proof['passed'] else 1
