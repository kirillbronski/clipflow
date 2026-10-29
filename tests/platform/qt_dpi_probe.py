"""Native/offscreen subprocess: one Qt scaling pass, all modes/languages at 880px."""
import os
from pathlib import Path

from PySide6.QtWidgets import QApplication
from clipflow.application.scheduler import Scheduler
from clipflow.application.submission import SubmissionService
from clipflow.domain.models import Service
from clipflow.infrastructure.executor import ThreadExecutor
from clipflow.infrastructure.settings import AppSettings
from clipflow.infrastructure.repository import SqliteJobRepository
from clipflow.ui.presenter import WorkbenchPresenter
from clipflow.ui.window import MainWindow

app=QApplication([])
repo=SqliteJobRepository(Path(os.environ['CLIPFLOW_DATA_DIR'])/'queue.sqlite3')
executor=ThreadExecutor({},None)
presenter=WorkbenchPresenter(SubmissionService(repo),Scheduler(repo,executor),AppSettings(),repo)
window=MainWindow(presenter); window.resize(880,680); window.show(); app.processEvents()
try:
    scale=float(os.environ['QT_SCALE_FACTOR'])
    expected=scale*float(os.environ['CLIPFLOW_BASE_DPR'])
    assert abs(window.devicePixelRatioF()-expected)<.1,(window.devicePixelRatioF(),expected)
    for language in ('ru','en'):
        window.language_actions[language].trigger()
        for mode in ('dark','light','system'):
            window.theme_actions[mode].trigger()
            for service in Service:
                window.composer.set_service(service); window.composer.parameters_button.setChecked(True)
                if service==Service.INSTAGRAM: window.composer.mode_buttons['profile'].click()
                app.processEvents()
                assert window.width()==880 and window.height()==680
                assert window.composer_host.horizontalScrollBar().maximum()==0,(language,mode,service)
                assert window.url_input.width()>=180
    print('PASS DPI '+os.environ['QT_SCALE_FACTOR']+' '+app.platformName())
finally:
    window.close(); executor.drain(); app.processEvents()
