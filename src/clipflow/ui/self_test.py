"""Real Qt/HTTP/FFmpeg package acceptance, fenced to a fresh explicit test root."""
import argparse
from dataclasses import replace
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from threading import Thread

from clipflow.version import APP_VERSION


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ui-self-test',action='store_true'); parser.add_argument('--data-dir',required=True)
    parser.add_argument('--report',required=True); parser.add_argument('--require-frozen',action='store_true')
    args=parser.parse_args(argv)
    if not os.environ.get('CLIPFLOW_DATA_DIR'): return 2
    isolated=Path(os.environ['CLIPFLOW_DATA_DIR']).resolve(); root=Path(args.data_dir).resolve(); report=Path(args.report).resolve()
    if (not root.is_relative_to(isolated) or not report.is_relative_to(isolated) or report==root
            or (root.exists() and any(root.iterdir()))): return 2
    root.mkdir(parents=True,exist_ok=True); report.parent.mkdir(parents=True,exist_ok=True)
    proof={'passed':False,'version':APP_VERSION,'ui':'qt','frozen':bool(getattr(sys,'frozen',False)),
           'os':platform.platform(),'cpu':platform.machine(),'local_transfer':False}
    if args.require_frozen and not proof['frozen']: return 2
    from clipflow.ui.bootstrap import create_application,_binary
    from clipflow.domain.models import Service,JobState
    from clipflow.providers.media import MediaPipeline
    from clipflow.providers.base import MediaItem,ExecutionContext
    from clipflow.domain.events import CancellationToken
    from PySide6.QtCore import QTimer
    app,window=create_application([],root)
    presenter=window.presenter; server=None; thread=None; outcomes=[]
    try:
        pipeline=MediaPipeline(ffmpeg=_binary('ffmpeg'),ffprobe=_binary('ffprobe'),node=_binary('node'))
        tools={name:_binary(name) for name in ('ffmpeg','ffprobe','node')}
        assert all(tools.values())
        if proof['frozen']:
            assert all(Path(p).resolve().is_relative_to(Path(sys._MEIPASS).resolve()) for p in tools.values())
        proof['tools']={name:Path(value).name for name,value in tools.items()}
        context=ExecutionContext(CancellationToken(),lambda event:None,presenter.auth_gateway,None)
        source=root/'fixture.mp4'
        pipeline._run([tools['ffmpeg'],'-v','error','-nostdin','-f','lavfi','-i',
            'color=c=blue:s=96x64:r=10','-f','lavfi','-i','sine=frequency=440:sample_rate=48000',
            '-t','0.3','-c:v','libx264','-c:a','aac','-y',str(source)],context)
        class LocalHandler(SimpleHTTPRequestHandler):
            def log_message(self,*args): pass
        server=ThreadingHTTPServer(('127.0.0.1',0),partial(LocalHandler,directory=str(root)))
        thread=Thread(target=server.serve_forever,daemon=True); thread.start()
        class LocalProvider:
            def execute(self,request,execution):
                return pipeline.save(MediaItem('local',1,'video','ClipFlow local package test',
                    {'id':'local','ext':'mp4','url':f'http://127.0.0.1:{server.server_port}/fixture.mp4'}),request,execution)
        # No network-capable provider remains reachable, including quality probes.
        presenter.executor.registry={key:LocalProvider() for key in presenter.executor.registry}
        options=replace(presenter.settings.presets[Service.YOUTUBE],folder=root/'downloads')
        assert presenter.update_preset(Service.YOUTUBE,options)
        def start():
            result=presenter.submit('https://youtu.be/CLIPFLOW_SELF_TEST')
            if result is None: app.exit(1); return
            presenter.start_queue()
        def poll():
            try:
                jobs=presenter.repository.list()
                if not jobs: return
                job=jobs[0]
                if job.state==JobState.FAILED: app.exit(1); return
                if job.state!=JobState.COMPLETED: return
                assert len(job.result_files)==1 and job.result_files[0].is_file()
                probe=pipeline._probe(job.result_files[0],context)
                assert {'audio','video'} <= {s['codec_type'] for s in probe['streams']}
                assert APP_VERSION in window.windowTitle() and presenter.executor.is_idle
                assert not window.windowIcon().isNull()
                window.resize(880,680); app.processEvents()
                assert window.queue_view.width()>300
                window.grab().save(str(root/'ui.png'))
                proof['local_transfer']=True; proof['files']=[p.name for p in job.result_files]
                outcomes.append(True); timer.stop(); window.close()
            except Exception: timer.stop(); app.exit(1)
        timer=QTimer(window); timer.setInterval(100); timer.timeout.connect(poll)
        window.show(); timer.start(); QTimer.singleShot(0,start); QTimer.singleShot(30000,lambda:app.exit(2))
        result=app.exec()
        proof['passed']=result==0 and bool(outcomes)
    except Exception:
        proof['error']='package_ui_self_test_failed'
    finally:
        presenter.shutdown(); presenter.executor.drain()
        presenter.auth_gateway.drain(); presenter._finish_shutdown(); window.dispose_ui()
        if server: server.shutdown(); server.server_close()
        if thread: thread.join(3)
        proof['worker_idle']=presenter.executor.is_idle
        proof['legacy_modules']=[name for name in ('tkinter','_tkinter','customtkinter') if name in sys.modules]
        proof['passed']=proof['passed'] and proof['worker_idle'] and not proof['legacy_modules']
        report.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return 0 if proof['passed'] else 1
