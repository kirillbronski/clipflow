"""Approved composition must leave space for the queue and retain real actions."""
from dataclasses import replace
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from clipflow.domain.models import Service, JobState, Job, DownloadRequest
from clipflow.domain.urls import parse_url
from clipflow.domain.events import ProgressChanged
from tests.ui.test_workbench import make_window, add


def test_collapsed_composer_leaves_queue_space_and_discloses_folder(make_window, qtbot):
    window, _ = make_window()
    window._navigate('instagram', False, 'Instagram')
    window.resize(1240, 792)
    qtbot.waitUntil(lambda: window.composer.width() > 500)
    assert window.composer.height() <= 220
    assert not window.folder_input.isVisible()
    assert not window.composer.service_box.isVisible()
    window.composer.parameters_button.click()
    qtbot.waitUntil(window.folder_input.isVisible)
    assert window.composer_host.horizontalScrollBar().maximum() == 0
    window.composer.parameters_button.click()
    qtbot.waitUntil(lambda: window.composer.height() <= 220)


def test_accounts_and_settings_stay_at_bottom_of_sidebar(make_window):
    window, _ = make_window()
    assert window.accounts_button.y() > window.height() * .65
    assert window.settings_button.y() > window.accounts_button.y()
    window.accounts_button.click()
    assert window.accounts_page.isVisible()
    window.settings_button.click()
    assert window.settings_page.isVisible()


def test_status_tabs_filter_actual_jobs_and_survive_service_change(make_window, qtbot):
    window, _ = make_window()
    identity = add(window, qtbot)
    original = window.presenter.repository.get(identity)
    window.presenter.repository.add(replace(original, id='done', state=JobState.COMPLETED))
    window.presenter.repository.add(replace(original, id='failed', state=JobState.FAILED))
    window.presenter._reload_jobs()
    window.status_buttons['completed'].click()
    assert window.proxy.rowCount() == 1
    assert window.proxy.index(0, 0).data(window.presenter.model.StateRole) == 'completed'
    window.status_buttons['active'].click()
    assert window.proxy.rowCount() == 1
    window.status_buttons['failed'].click()
    assert window.proxy.rowCount() == 1
    window._navigate('instagram', False, 'Instagram')
    assert window.proxy.rowCount() == 0
    window._navigate('youtube', False, 'YouTube')
    assert window.proxy.rowCount() == 1
    window.status_buttons['all'].click()
    assert window.proxy.rowCount() == 3


@pytest.mark.parametrize('service', list(Service))
def test_primary_and_progress_use_the_selected_service_accent(make_window, qtbot, service):
    window, _ = make_window()
    window._navigate(service.value, False, service.value)
    urls={Service.YOUTUBE:'https://youtu.be/ABC', Service.INSTAGRAM:'https://instagram.com/p/ABC/',Service.GETCOURSE:'https://school.getcourse.ru/pl/teach/control/lesson/view?id=123'}
    job=Job('color',DownloadRequest(parse_url(urls[service]),window.presenter.settings.presets[service]),state=JobState.DOWNLOADING)
    window.presenter.repository.add(job)
    window.presenter.model.update_job(job,ProgressChanged(50,100))
    qtbot.waitUntil(lambda: window.proxy.rowCount()==1)
    window.queue_view.repaint()
    expected=QColor(window.theme.tokens()[service.value])
    image=window.queue_view.viewport().grab().toImage()
    dpr=image.devicePixelRatio()
    assert image.pixelColor(int(64*dpr),int(72*dpr))==expected
    button=window.add_button.grab().toImage()
    actual=button.pixelColor(int((window.add_button.width()-8)*button.devicePixelRatio()),int(window.add_button.height()/2*button.devicePixelRatio()))
    difference=abs(actual.hueF()-expected.hueF())
    assert min(difference,1-difference)<.08


@pytest.mark.parametrize('mode', ['light', 'dark'])
@pytest.mark.parametrize('language', ['ru', 'en'])
def test_design_disclosure_and_navigation_fit_minimum_window(make_window, qtbot, mode, language):
    window, _ = make_window()
    window.theme_actions[mode].trigger()
    window.language_actions[language].trigger()
    window.resize(880, 680)
    for service in Service:
        window._navigate(service.value, False, service.value)
        window.composer.parameters_button.setChecked(True)
        qtbot.waitUntil(lambda: window.composer_host.horizontalScrollBar().maximum() == 0)
        assert window.url_input.width() >= 180
        assert window.queue_view.height() >= 70
        assert window.composer.add_button.width() >= window.composer.add_button.fontMetrics().horizontalAdvance(window.composer.add_button.text()) + 12
