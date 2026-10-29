from dataclasses import replace

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox
import pytest

from clipflow.domain.models import Job, JobState, DownloadRequest, DownloadOptions
from clipflow.domain.urls import parse_url
from tests.ui.test_workbench import make_window


def completed(window, tmp_path, identity='done', files=None):
    root=tmp_path/'downloads'; root.mkdir(exist_ok=True)
    target=root/'author'/'post'/'video.mp4'; target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(b'finished media')
    job=Job(identity,DownloadRequest(parse_url('https://youtu.be/'+identity),DownloadOptions(root)),
            state=JobState.COMPLETED,result_files=files if files is not None else (target,))
    window.presenter.repository.add(job); window.presenter.model.set_jobs(window.presenter.repository.list())
    return job,target


def test_clear_keeps_files(make_window,tmp_path):
    window,_=make_window(); job,target=completed(window,tmp_path)
    queued=replace(job,id='queued',state=JobState.QUEUED,result_files=())
    window.presenter.repository.add(queued)
    window.presenter.clear_queue()
    assert [j.id for j in window.presenter.repository.list()]==[job.id]
    window.presenter.clear_history()
    assert window.presenter.model.rowCount()==0 and target.read_bytes()==b'finished media'


def test_delete_requires_confirmation_and_containment(make_window,tmp_path):
    window,_=make_window(); job,target=completed(window,tmp_path)
    window.presenter.delete_files((job.id,),False)
    assert target.exists()
    outside=tmp_path/'outside.mp4'; outside.write_bytes(b'keep')
    window.presenter.repository.update(replace(job,result_files=(target,outside)))
    window.presenter.delete_files((job.id,),True)
    assert outside.exists() and target.exists()  # Preflight every path before deleting any.
    window.presenter.repository.update(job)
    window.presenter.delete_files((job.id,),True)
    assert not target.exists() and outside.exists()
    assert window.presenter.repository.get(job.id).state==JobState.COMPLETED


def test_open_uses_resolved_post_folder(make_window,tmp_path,monkeypatch):
    window,_=make_window(); job,target=completed(window,tmp_path); opened=[]
    monkeypatch.setattr(QDesktopServices,'openUrl',lambda url:opened.append(url) or True)
    window.presenter.open_result(job.id)
    assert opened==[QUrl.fromLocalFile(str(target.parent.resolve()))]


def test_deleted_file_history_is_honest(make_window,tmp_path,monkeypatch):
    window,_=make_window(); job,target=completed(window,tmp_path); target.unlink(); errors=[]; opened=[]
    window.presenter.error_raised.connect(errors.append)
    monkeypatch.setattr(QDesktopServices,'openUrl',lambda url:opened.append(url))
    window.presenter.open_result(job.id)
    assert errors==['files_missing'] and not opened
    from clipflow.ui.history import result_status
    assert result_status(job)=='files_missing'


def test_repeat_uses_saved_request_not_composer(make_window,tmp_path):
    window,_=make_window(); job,_=completed(window,tmp_path)
    window.url_input.setText('https://youtu.be/DIFFERENT')
    window.presenter.repeat_job(job.id)
    jobs=window.presenter.repository.list()
    assert len(jobs)==2 and jobs[-1].request==job.request


def test_ui_delete_confirmation_and_list_only_removal(make_window,tmp_path,qtbot):
    window,_=make_window(); job,target=completed(window,tmp_path)
    window._confirm_delete((job.id,))
    box=window.findChild(QMessageBox)
    assert box is not None and target.exists()
    box.button(QMessageBox.StandardButton.No).click()
    assert target.exists()
    window._confirm_delete((job.id,))
    box=window._dialogs[-1]; box.button(QMessageBox.StandardButton.Yes).click()
    assert not target.exists()
    window.presenter.remove_jobs((job.id,))
    assert not window.presenter.repository.list()


def test_cannot_delete_file_used_by_active_job(make_window,tmp_path):
    window,_=make_window(); job,target=completed(window,tmp_path)
    window.presenter.repository.add(replace(job,id='other',state=JobState.DOWNLOADING))
    window.presenter.delete_files((job.id,),True)
    assert target.exists()


def test_symlink_escape_is_rejected(make_window,tmp_path):
    window,_=make_window(); job,target=completed(window,tmp_path)
    outside=tmp_path/'external'; outside.mkdir(); link=target.parent/'escape'
    try: link.symlink_to(outside,target_is_directory=True)
    except OSError: pytest.skip('Symlink creation unavailable on this host')
    victim=outside/'keep.mp4'; victim.write_bytes(b'keep')
    window.presenter.repository.update(replace(job,result_files=(link/'keep.mp4',)))
    window.presenter.delete_files((job.id,),True)
    assert victim.exists()


def test_clear_waits_for_active_worker_and_never_starts_next(make_window,tmp_path,qtbot):
    window,provider=make_window(); job,target=completed(window,tmp_path)
    repo=window.presenter.repository
    repo.add(replace(job,id='active',state=JobState.QUEUED,result_files=()))
    repo.add(replace(job,id='next',state=JobState.QUEUED,result_files=()))
    window.presenter.start_queue(); qtbot.waitUntil(provider.started.is_set)
    window.presenter.clear_queue()
    qtbot.waitUntil(lambda:[j.id for j in repo.list()]==[job.id])
    assert provider.torn_down.is_set() and target.exists()
    assert window.presenter.executor.is_idle


def test_history_clear_during_cancel_ack_keeps_worker_record(make_window,tmp_path,qtbot):
    window,provider=make_window(); job,target=completed(window,tmp_path)
    repo=window.presenter.repository
    repo.add(replace(job,id='active',state=JobState.QUEUED,result_files=()))
    window.presenter.start_queue(); qtbot.waitUntil(provider.started.is_set)
    window.presenter.cancel_job('active'); window.presenter.clear_history()
    assert repo.get('active').state==JobState.CANCELLED
    qtbot.waitUntil(lambda:window.presenter.executor.is_idle)
    assert not window.presenter.is_closed


def test_history_context_menu_has_localized_actions(make_window,tmp_path,qtbot):
    from PySide6.QtWidgets import QMenu
    window,_=make_window(); job,target=completed(window,tmp_path)
    window.presenter._reload_jobs()
    index=window.proxy.index(0,0); window.queue_view.setCurrentIndex(index)
    window._history_menu(window.queue_view.visualRect(index).center())
    menu=window.findChildren(QMenu)[-1]
    assert any(a.text()==window.tr.text('delete_files') for a in menu.actions())
    menu.close()


def test_history_counts_visible_results_and_hides_queue_start(make_window,tmp_path):
    window,_=make_window(); job,target=completed(window,tmp_path)
    window.presenter.repository.add(replace(job,id='waiting',state=JobState.QUEUED,result_files=()))
    window.presenter._reload_jobs(); window._navigate(None,True,'history')
    assert not window.start_button.isVisible()
    assert window.count_label.text()==window.tr.text('history_count',count=1)


def test_history_parent_is_kept_for_live_child(make_window,tmp_path):
    window,_=make_window(); job,target=completed(window,tmp_path)
    window.presenter.repository.add(replace(job,id='child',parent_id=job.id,state=JobState.QUEUED,result_files=()))
    window.presenter.clear_history()
    assert len(window.presenter.repository.list())==2
    window.presenter.remove_jobs((job.id,))
    assert len(window.presenter.repository.list())==2 and target.exists()


def test_file_delete_failure_reports_and_keeps_record(make_window,tmp_path,monkeypatch):
    from pathlib import Path
    window,_=make_window(); job,target=completed(window,tmp_path); errors=[]
    window.presenter.error_raised.connect(errors.append)
    original=Path.unlink
    def denied(path,*args,**kwargs):
        if path==target: raise PermissionError('locked')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'unlink',denied)
    window.presenter.delete_files((job.id,),True)
    assert errors==['file_delete_failed'] and target.exists()
    assert window.presenter.repository.get(job.id).result_files==(target,)


def test_delete_during_cancel_ack_keeps_files(make_window,tmp_path,qtbot):
    window,provider=make_window(); job,target=completed(window,tmp_path)
    repo=window.presenter.repository
    repo.add(replace(job,id='active',state=JobState.QUEUED))
    window.presenter.start_queue(); qtbot.waitUntil(provider.started.is_set)
    window.presenter.cancel_job('active'); window.presenter.delete_files(('active',),True)
    assert target.exists()
    qtbot.waitUntil(lambda:window.presenter.executor.is_idle)
