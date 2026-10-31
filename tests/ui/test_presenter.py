"""Workbench commands: what each one changes, and the code the window shows when it cannot."""

import pytest
from PySide6.QtGui import QDesktopServices

from clipflow.application.scheduler import Scheduler
from clipflow.application.submission import SubmissionService
from clipflow.domain.models import (
    ContentKind,
    DownloadOptions,
    DownloadRequest,
    Job,
    JobState,
    Service,
)
from clipflow.domain.urls import parse_url
from clipflow.infrastructure.auth import AuthStatus
from clipflow.infrastructure.executor import ThreadExecutor
from clipflow.infrastructure.repository import SqliteJobRepository
from clipflow.infrastructure.settings import AppSettings
from clipflow.ui.presenter import WorkbenchPresenter
from tests.instagram_fixtures import Auth
from tests.support.workbench import HeldProvider


@pytest.fixture
def provider():
    return HeldProvider()


@pytest.fixture
def repository(tmp_path):
    repository = SqliteJobRepository(tmp_path / 'queue.sqlite3')
    yield repository
    repository.close()


@pytest.fixture
def presenter(qtbot, tmp_path, provider, repository):
    presets = {s: DownloadOptions(tmp_path / 'downloads') for s in Service}
    registry = {
        (Service.YOUTUBE, ContentKind.VIDEO): provider,
        (Service.GETCOURSE, ContentKind.LESSON): provider,
    }
    executor = ThreadExecutor(registry, Auth())
    presenter = WorkbenchPresenter(
        SubmissionService(repository),
        Scheduler(repository, executor),
        AppSettings(presets=presets),
        repository,
    )
    yield presenter
    provider.released.set()
    presenter.shutdown()
    qtbot.waitUntil(lambda: presenter.is_closed, timeout=5000)


def recorded(signal):
    values = []
    signal.connect(lambda *args: values.append(args[0] if len(args) == 1 else args))
    return values


# A lesson link with a secret: only a reference is stored, the link itself is asked for again.
SECRET_LESSON = 'https://school.getcourse.ru/pl/teach/control/lesson/view?id=1&token=private'


def saved(repository, tmp_path, url='https://youtu.be/ABC', **fields):
    request = DownloadRequest(parse_url(url), DownloadOptions(tmp_path / 'downloads'))
    job = Job('job-1', request, **fields)
    repository.add(job)
    return job.id


def test_commands_after_closing_report_app_closed_and_change_nothing(presenter):
    errors = recorded(presenter.error_raised)
    presenter.shutdown()
    assert presenter.submit('https://youtu.be/ABC') is None
    assert errors == ['app_closed']
    assert presenter.model.rowCount() == 0


@pytest.mark.parametrize('text', ['not a link', 'https://www.instagram.com/someone/'])
def test_unusable_text_answers_the_quality_probe_with_invalid_link(presenter, text):
    answers = recorded(presenter.probe_ready)
    presenter.request_probe(text, 'probe-1')
    assert answers == [('probe-1', (), 'invalid_link')]


@pytest.mark.parametrize('state', [JobState.FAILED, JobState.CANCELLED])
def test_activating_a_stopped_job_downloads_it_again(
    presenter, provider, repository, tmp_path, state, qtbot
):
    identity = saved(repository, tmp_path, state=state, error='network_failed')
    presenter.toggle_job(identity)
    qtbot.waitUntil(provider.started.is_set)
    assert repository.get(identity).error is None


def test_job_without_its_source_asks_for_it_on_activate_and_repeat(presenter, repository, tmp_path):
    asked = recorded(presenter.source_requested)
    identity = saved(
        repository, tmp_path, SECRET_LESSON, state=JobState.FAILED, source_required=True
    )
    presenter.toggle_job(identity)
    presenter.repeat_job(identity)
    assert asked == [identity, identity]
    assert repository.get(identity).state == JobState.FAILED


def test_providing_the_same_source_resumes_the_job(
    presenter, provider, repository, tmp_path, qtbot
):
    identity = saved(
        repository, tmp_path, SECRET_LESSON, state=JobState.PAUSED, source_required=True
    )
    presenter.provide_source(identity, SECRET_LESSON)
    qtbot.waitUntil(provider.started.is_set)
    assert not repository.get(identity).source_required


def test_providing_a_different_source_is_refused(presenter, repository, tmp_path):
    errors = recorded(presenter.error_raised)
    identity = saved(
        repository, tmp_path, SECRET_LESSON, state=JobState.PAUSED, source_required=True
    )
    presenter.provide_source(identity, SECRET_LESSON.replace('private', 'other'))
    assert errors == ['source_changed']
    assert repository.get(identity).source_required


def test_repeating_a_failed_job_retries_it_and_autostarts(
    presenter, provider, repository, tmp_path, qtbot
):
    presenter.set_auto_start(True)
    identity = saved(repository, tmp_path, state=JobState.FAILED, error='network_failed')
    presenter.repeat_job(identity)
    qtbot.waitUntil(provider.started.is_set)
    assert [job.id for job in repository.list()] == [identity]


def test_opening_a_result_whose_folder_is_gone_reports_it(
    presenter, repository, tmp_path, monkeypatch
):
    opened = []
    monkeypatch.setattr(QDesktopServices, 'openUrl', staticmethod(opened.append))
    errors = recorded(presenter.error_raised)
    identity = saved(repository, tmp_path, state=JobState.COMPLETED)
    presenter.open_result(identity)
    assert errors == ['folder_missing']
    assert opened == []


def test_opening_a_result_the_system_refuses_reports_it(
    presenter, repository, tmp_path, monkeypatch
):
    (tmp_path / 'downloads').mkdir()
    monkeypatch.setattr(QDesktopServices, 'openUrl', staticmethod(lambda url: False))
    errors = recorded(presenter.error_raised)
    identity = saved(repository, tmp_path, state=JobState.COMPLETED)
    presenter.open_result(identity)
    assert errors == ['folder_missing']


def test_new_folder_is_saved_for_the_service_and_remembered(presenter, tmp_path):
    changed = recorded(presenter.settings_changed)
    folder = tmp_path / 'music'
    assert presenter.update_folder(Service.YOUTUBE, str(folder))
    assert presenter.settings.presets[Service.YOUTUBE].folder == folder.resolve()
    assert presenter.settings.presets[Service.INSTAGRAM].folder == tmp_path / 'downloads'
    assert presenter.settings.recent_folders[0] == folder.resolve()
    assert len(changed) == 1


def test_queue_write_failure_on_close_is_reported_and_close_completes(
    presenter, qtbot, monkeypatch
):
    errors = recorded(presenter.error_raised)

    def broken():
        raise OSError('disk full')

    monkeypatch.setattr(presenter.scheduler, 'shutdown', broken)
    presenter.shutdown()
    assert errors == ['queue_update_failed']
    qtbot.waitUntil(lambda: presenter.is_closed)


class Gateway:
    """An account store with one GetCourse school and no browser sign-in."""

    def __init__(self):
        self.polls = 0
        self.imported = []
        self.logged_out = []
        self.profile = None

    def activate_profile(self, service, profile):
        pass

    def poll(self):
        self.polls += 1

    def status(self, service):
        if service == Service.GETCOURSE and self.profile:
            return AuthStatus(service, self.profile, True, 'configured')
        return AuthStatus(service)

    def import_legacy_getcourse(self, url):
        self.imported.append(url)
        self.profile = 'gc-' + '0' * 24
        return self.profile

    def logout(self, profile):
        self.logged_out.append(profile)

    def close(self):
        pass

    is_closed = True


def test_account_commands_without_an_account_store_do_nothing(presenter):
    assert presenter.sign_in_account(Service.YOUTUBE) is None
    assert presenter.import_getcourse('https://school.getcourse.ru/') is None
    assert presenter.configure_getcourse('https://school.getcourse.ru/', 'public') is None
    assert presenter.logout_account(Service.YOUTUBE) is None


def test_imported_school_profile_becomes_the_getcourse_preset(presenter):
    gateway = Gateway()
    presenter.set_auth_gateway(gateway)
    profile = presenter.import_getcourse('https://school.getcourse.ru/')
    assert presenter.settings.presets[Service.GETCOURSE].auth_profile == profile


def test_unchanged_accounts_do_not_notify_the_window(presenter):
    gateway = Gateway()
    presenter.set_auth_gateway(gateway)
    changes = recorded(presenter.auth_changed)
    presenter._poll_auth()
    assert gateway.polls == 2
    assert changes == []


def test_signing_out_of_a_service_without_a_profile_does_nothing(presenter):
    gateway = Gateway()
    presenter.set_auth_gateway(gateway)
    presenter.logout_account(Service.YOUTUBE)
    assert gateway.logged_out == []


def test_account_store_attached_after_close_is_not_polled(presenter):
    presenter.shutdown()
    errors = recorded(presenter.error_raised)
    gateway = Gateway()
    presenter.set_auth_gateway(gateway)
    assert gateway.polls == 0
    assert errors == []
