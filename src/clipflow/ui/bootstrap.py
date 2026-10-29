"""Explicit Qt preview bootstrap, isolated from the legacy Tk entry point."""
import os
from pathlib import Path
import shutil
import sys

from PySide6.QtWidgets import QApplication,QMessageBox

from clipflow.application.scheduler import Scheduler
from clipflow.application.submission import SubmissionService
from clipflow.application.instagram_rate_policy import InstagramRatePolicy
from clipflow.domain.models import Service,ContentKind
from clipflow.infrastructure.executor import ThreadExecutor
from clipflow.infrastructure.repository import SqliteJobRepository,RepositoryError
from clipflow.infrastructure.settings import SettingsStore,SettingsError,AppSettings
from clipflow.infrastructure.rate_limit_store import RateLimitStore
from clipflow.providers.media import MediaPipeline
from clipflow.providers.youtube import YouTubeProvider
from clipflow.providers.getcourse import GetCourseProvider
from clipflow.providers.instagram_post import InstagramPostProvider
from clipflow.providers.instagram_profile import InstagramProfileProvider,InstaloaderPageSource
from clipflow.ui.presenter import WorkbenchPresenter
from clipflow.ui.window import MainWindow
from clipflow.ui.i18n import Translator,CATALOG
from clipflow.ui.themes import ThemeManager
from clipflow.infrastructure.auth import NativeAuthGateway
from clipflow.infrastructure.platform import data_directory


def _binary(name):
    executable=name+('.exe' if sys.platform=='win32' else '')
    root=Path(__file__).resolve().parents[3]
    for folder in (Path(getattr(sys,'_MEIPASS',root))/'bin',root/'.runtime'/('windows' if sys.platform=='win32' else 'macos')/'bin'):
        if (folder/executable).is_file(): return str(folder/executable)
    return shutil.which(executable)


def create_application(argv:list[str],data_dir:Path|None=None):
    app=QApplication.instance() or QApplication(argv)
    app.setApplicationName('ClipFlow')
    directory=Path(data_dir) if data_dir is not None else data_directory()
    settings_store=SettingsStore(directory); settings=settings_store.load()
    app.setProperty('clipflowLanguage',settings.language); app.setProperty('clipflowTheme',settings.theme)
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
        auth=NativeAuthGateway(directory)
        executor=ThreadExecutor(registry,auth,instagram_rate=policy,cleanup=source.close)
        scheduler=Scheduler(repository,executor)
        presenter=WorkbenchPresenter(SubmissionService(repository),scheduler,settings,repository,settings_store=settings_store)
        presenter.set_auth_gateway(auth)
        window=MainWindow(presenter)
        if settings_store.last_warning: window._show_error(settings_store.last_warning)
        app.aboutToQuit.connect(presenter.shutdown)
        return app,window
    except BaseException:
        repository.close(); raise


def main(argv=None):
    arguments=list(sys.argv if argv is None else argv)
    from clipflow.infrastructure.auth_process.__main__ import FLAGS
    if any(flag in arguments for flag in FLAGS):
        from clipflow.infrastructure.auth_process.__main__ import main as auth_main
        return auth_main(arguments[1:])
    try: app,window=create_application(arguments)
    except (RepositoryError,SettingsError) as error:
        app=QApplication.instance()
        settings=AppSettings(language=app.property('clipflowLanguage') or 'ru',theme=app.property('clipflowTheme') or 'dark')
        theme=ThemeManager(app,settings); translator=Translator(settings.language); translator.install_qt()
        key='error.'+error.code
        QMessageBox.critical(None,'ClipFlow',translator.text(key if key in CATALOG[translator.language] else 'error.generic'))
        return 1
    window.show()
    try: return app.exec()
    finally:
        window.presenter.shutdown(); window.presenter.executor.drain()
        if window.presenter.auth_gateway is not None:
            window.presenter.auth_gateway.drain(); window.presenter._finish_shutdown()
        window.dispose_ui()
