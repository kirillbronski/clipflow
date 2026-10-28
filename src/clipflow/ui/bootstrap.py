"""Explicit Qt preview bootstrap, isolated from the legacy Tk entry point."""
import os
from pathlib import Path
import shutil
import sys

from PySide6.QtGui import QColor,QPalette,QIcon,QPixmap,QPainter,QPen
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication,QMessageBox

from clipflow.application.scheduler import Scheduler
from clipflow.application.submission import SubmissionService
from clipflow.application.instagram_rate_policy import InstagramRatePolicy
from clipflow.domain.models import Service,ContentKind
from clipflow.infrastructure.executor import ThreadExecutor
from clipflow.infrastructure.repository import SqliteJobRepository,RepositoryError
from clipflow.infrastructure.settings import SettingsStore,SettingsError
from clipflow.infrastructure.rate_limit_store import RateLimitStore
from clipflow.providers.base import MediaFailure
from clipflow.providers.media import MediaPipeline
from clipflow.providers.youtube import YouTubeProvider
from clipflow.providers.getcourse import GetCourseProvider
from clipflow.providers.instagram_post import InstagramPostProvider
from clipflow.providers.instagram_profile import InstagramProfileProvider,InstaloaderPageSource
from clipflow.ui.presenter import WorkbenchPresenter
from clipflow.ui.window import MainWindow


class PublicAuthGateway:
    """Real protected-storage adapters are T13; do not pretend a login succeeded."""
    def options_for(self,profile,url):
        if profile is not None: raise MediaFailure('auth_required')
        return {}


def data_directory():
    if os.environ.get('CLIPFLOW_DATA_DIR'): return Path(os.environ['CLIPFLOW_DATA_DIR']).expanduser().resolve()
    if sys.platform=='darwin': return Path.home()/'Library'/'Application Support'/'ClipFlow'
    return Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'ClipFlow'


def _binary(name):
    executable=name+('.exe' if sys.platform=='win32' else '')
    root=Path(__file__).resolve().parents[3]
    for folder in (Path(getattr(sys,'_MEIPASS',root))/'bin',root/'.runtime'/('windows' if sys.platform=='win32' else 'macos')/'bin'):
        if (folder/executable).is_file(): return str(folder/executable)
    return shutil.which(executable)


def _dark(app):
    app.setStyle('Fusion')
    palette=QPalette()
    for role,color in [(QPalette.ColorRole.Window,'#1c1e25'),(QPalette.ColorRole.Base,'#1c1e25'),
                       (QPalette.ColorRole.AlternateBase,'#24262f'),(QPalette.ColorRole.WindowText,'#eeedf5'),
                       (QPalette.ColorRole.Text,'#eeedf5'),(QPalette.ColorRole.Button,'#24262f'),
                       (QPalette.ColorRole.ButtonText,'#eeedf5'),(QPalette.ColorRole.Highlight,'#6752b2'),
                       (QPalette.ColorRole.HighlightedText,'#ffffff')]: palette.setColor(role,QColor(color))
    app.setPalette(palette)


def _icon():
    pixmap=QPixmap(64,64); pixmap.fill(Qt.GlobalColor.transparent); painter=QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing); painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(QColor('#8975ed'))
    painter.drawRoundedRect(2,2,60,60,14,14); painter.setPen(QPen(QColor('white'),5,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
    painter.drawLine(32,16,32,45); painter.drawLine(21,34,32,45); painter.drawLine(32,45,43,34); painter.end()
    return QIcon(pixmap)


def create_application(argv:list[str],data_dir:Path|None=None):
    app=QApplication.instance() or QApplication(argv)
    app.setApplicationName('ClipFlow'); _dark(app); app.setWindowIcon(_icon())
    directory=Path(data_dir) if data_dir is not None else data_directory()
    settings_store=SettingsStore(directory); settings=settings_store.load()
    repository=SqliteJobRepository(directory/'queue.sqlite3')
    try:
        repository.recover()
        source=InstaloaderPageSource()
        pipeline=MediaPipeline(ffmpeg=_binary('ffmpeg'),ffprobe=_binary('ffprobe'),node=_binary('node'))
        youtube=YouTubeProvider(pipeline); getcourse=GetCourseProvider(pipeline)
        registry={(Service.YOUTUBE,kind):youtube for kind in (ContentKind.VIDEO,ContentKind.PLAYLIST)}
        registry.update({(Service.GETCOURSE,kind):getcourse for kind in (ContentKind.LESSON,ContentKind.PLAYER)})
        registry[(Service.INSTAGRAM,ContentKind.POST)]=InstagramPostProvider(pipeline)
        registry[(Service.INSTAGRAM,ContentKind.PROFILE)]=InstagramProfileProvider(source)
        policy=InstagramRatePolicy(RateLimitStore(directory/'instagram-rate.sqlite3'))
        executor=ThreadExecutor(registry,PublicAuthGateway(),instagram_rate=policy,cleanup=source.close)
        scheduler=Scheduler(repository,executor)
        presenter=WorkbenchPresenter(SubmissionService(repository),scheduler,settings,repository,settings_store=settings_store)
        window=MainWindow(presenter)
        if settings_store.last_warning: window._show_error(settings_store.last_warning)
        app.aboutToQuit.connect(presenter.shutdown)
        return app,window
    except BaseException:
        repository.close(); raise


def main(argv=None):
    try: app,window=create_application(list(sys.argv if argv is None else argv))
    except (RepositoryError,SettingsError) as error:
        messages={'storage_read_only':'Нет доступа для записи в папку данных ClipFlow. Проверьте права доступа.',
                  'storage_busy':'Хранилище ClipFlow занято. Закройте другую копию приложения и повторите запуск.',
                  'queue_corrupt':'Файл очереди повреждён. Исходный файл сохранён; восстановите его из резервной копии.',
                  'unsupported_queue_schema':'Данные очереди созданы другой версией ClipFlow. Используйте совместимую версию.',
                  'unsupported_settings_schema':'Настройки созданы другой версией ClipFlow. Используйте совместимую версию.'}
        QMessageBox.critical(None,'ClipFlow',messages.get(error.code,'Не удалось открыть данные ClipFlow. Проверьте папку данных.'))
        return 1
    window.show()
    try: return app.exec()
    finally:
        window.presenter.shutdown(); window.presenter.executor.drain()
