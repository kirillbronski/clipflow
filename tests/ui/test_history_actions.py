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


def test_visible_cancel_queue_stops_all_workers_and_keeps_files(make_window,tmp_path,qtbot):
    window,provider=make_window(); job,target=completed(window,tmp_path)
    repo=window.presenter.repository
    for identity in ('active','next'):
        repo.add(replace(job,id=identity,state=JobState.QUEUED,result_files=()))
    window.presenter._reload_jobs(); window.presenter.start_queue(); qtbot.waitUntil(provider.started.is_set)
    window.cancel_queue_button.click()
    qtbot.waitUntil(lambda:window.presenter.executor.is_idle)
    assert all(j.state in {JobState.CANCELLED,JobState.COMPLETED} for j in repo.list())
    assert len(repo.list())==3 and target.read_bytes()==b'finished media'
    assert provider.torn_down.is_set()


def test_clear_all_button_confirms_then_stops_and_clears_across_services(make_window,tmp_path,qtbot):
    window,provider=make_window(); job,target=completed(window,tmp_path)
    repo=window.presenter.repository
    child=replace(job,id='child',parent_id=job.id,state=JobState.QUEUED,result_files=())
    repo.add(child); repo.add(replace(child,id='instagram',parent_id=None,request=replace(child.request,link=parse_url('https://instagram.com/p/ABC/'))))
    window.presenter._reload_jobs(); window.presenter.start_queue(); qtbot.waitUntil(provider.started.is_set)
    window._navigate('instagram',False,'Instagram')
    window.clear_all_button.click(); dialog=window._dialogs[-1]
    dialog.button(QMessageBox.StandardButton.No).click()
    assert len(repo.list())==3
    window.clear_all_button.click(); dialog=window._dialogs[-1]
    dialog.button(QMessageBox.StandardButton.Yes).click()
    qtbot.waitUntil(lambda:not repo.list())
    assert window.presenter.executor.is_idle and provider.torn_down.is_set()
    assert target.read_bytes()==b'finished media'
    assert window.presenter.model.rowCount()==0


@pytest.mark.parametrize('language',['ru','en'])
def test_queue_bulk_controls_fit_and_hide_in_settings(make_window,qtbot,language):
    window,_=make_window(); window.language_actions[language].trigger(); window.resize(880,680)
    qtbot.waitUntil(lambda:window.main_page.viewport().width()>500)
    for button in (window.start_button,window.cancel_queue_button,window.clear_all_button):
        assert button.isVisible()
        assert button.width()>=button.fontMetrics().horizontalAdvance(button.text())+10
    window.settings_button.click()
    assert not window.cancel_queue_button.isVisible() and not window.clear_all_button.isVisible()
    window._navigate(None,True,'history')
    assert window.clear_all_button.isVisible() and not window.cancel_queue_button.isVisible()


def test_clear_all_optional_file_deletion_waits_for_worker(make_window,tmp_path,qtbot):
    window,provider=make_window(); job,target=completed(window,tmp_path)
    window.presenter.repository.add(replace(job,id='active',state=JobState.QUEUED,result_files=()))
    window.presenter._reload_jobs(); window.presenter.start_queue(); qtbot.waitUntil(provider.started.is_set)
    window.clear_all_button.click(); dialog=window._dialogs[-1]
    assert not dialog.checkBox().isChecked()
    dialog.checkBox().setChecked(True)
    dialog.button(QMessageBox.StandardButton.Yes).click()
    qtbot.waitUntil(lambda:not window.presenter.repository.list())
    assert provider.torn_down.is_set() and window.presenter.executor.is_idle
    assert not target.exists()


def test_clear_all_delete_failure_keeps_records_and_does_not_retry(make_window,tmp_path,monkeypatch,qtbot):
    from pathlib import Path
    window,_=make_window(); job,target=completed(window,tmp_path)
    errors=[]; attempts=[]; window.presenter.error_raised.connect(errors.append)
    original=Path.unlink
    def fail(path,*args,**kwargs):
        if path==target: attempts.append(path); raise PermissionError('locked')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'unlink',fail)
    window.presenter.clear_all(delete_files=True)
    window.presenter._tick(); window.presenter._tick()
    assert errors==['file_delete_failed'] and len(attempts)==1
    assert target.exists() and len(window.presenter.repository.list())==1


def test_clear_all_rejects_escaped_recorded_file(make_window,tmp_path):
    window,_=make_window(); outside=tmp_path/'outside.mp4'; outside.write_bytes(b'keep')
    job,target=completed(window,tmp_path,files=(outside,))
    errors=[]; window.presenter.error_raised.connect(errors.append)
    window.presenter.clear_all(delete_files=True)
    assert errors==['unsafe_result_path']
    assert outside.exists() and window.presenter.repository.list()


def test_empty_clear_does_not_arm_later_file_deletion(make_window,tmp_path):
    window,_=make_window()
    window.presenter.clear_all(delete_files=True)
    job,target=completed(window,tmp_path)
    window.presenter.repository.update(replace(job,state=JobState.PAUSED))
    window.presenter.clear_queue()
    assert target.exists()


@pytest.mark.parametrize('delete_second',[False,True])
def test_overlapping_clear_commands_keep_deletion_consent_per_snapshot(make_window,tmp_path,monkeypatch,delete_second):
    window,_=make_window(); first,first_file=completed(window,tmp_path)
    executor=window.presenter.executor
    with monkeypatch.context() as patch:
        patch.setattr(type(executor),'is_idle',property(lambda self:False))
        window.presenter.clear_all(delete_files=True)
        second_root=tmp_path/'second'; second_root.mkdir()
        second,second_file=completed(window,second_root,identity='second')
        window.presenter.clear_all(delete_files=delete_second)
        assert first_file.exists() and second_file.exists()
    window.presenter._tick()
    assert not window.presenter.repository.list()
    assert first_file.exists() is (not delete_second)
    assert second_file.exists() is (not delete_second)


@pytest.mark.parametrize('language',['ru','en'])
def test_bulk_toolbar_wraps_wide_metrics_without_growing_minimum_window(make_window,qtbot,language):
    window,_=make_window(); window.language_actions[language].trigger()
    window.count_label.setMinimumWidth(180)
    for button in (window.start_button,window.cancel_queue_button,window.clear_all_button):
        button.setMinimumWidth(180)
    window.resize(880,680)
    qtbot.wait(60)  # Let native minimum-size propagation settle before assertions.
    qtbot.waitUntil(lambda:window.width()==880 and window.main_page.horizontalScrollBar().maximum()==0)
    # The actions may also stack if the real fallback font needs more than
    # 180px per label; readable non-overlapping controls are the contract.
    rectangles=[b.geometry() for b in (window.start_button,window.cancel_queue_button,window.clear_all_button)]
    assert all(not a.intersects(b) for i,a in enumerate(rectangles) for b in rectangles[i+1:])
    assert window.clear_all_button.isVisible()


def test_bulk_toolbar_very_wide_buttons_stack_without_horizontal_scroll(make_window,qtbot):
    window,_=make_window()
    for button in (window.start_button,window.cancel_queue_button,window.clear_all_button):
        button.setMinimumWidth(300)
    window.resize(880,680)
    qtbot.waitUntil(lambda:window.cancel_queue_button.y()>window.start_button.y())
    assert window.width()==880
    assert window.clear_all_button.y()>window.cancel_queue_button.y()
    assert window.main_page.horizontalScrollBar().maximum()==0
