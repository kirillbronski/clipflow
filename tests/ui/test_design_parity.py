"""Approved composition must leave space for the queue and retain real actions."""

from dataclasses import replace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from clipflow.domain.events import ProgressChanged
from clipflow.domain.models import DownloadRequest, Job, JobState, Service
from clipflow.domain.urls import parse_url
from tests.ui.test_workbench import add, make_window


def test_collapsed_composer_leaves_queue_space_and_discloses_folder(make_window, qtbot):
    window, _ = make_window()
    window._navigate('instagram', False, 'Instagram')
    window.resize(1240, 792)
    qtbot.waitUntil(lambda: window.composer.width() > 500 and window.composer.height() <= 220)
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
    assert window.accounts_button.y() > window.height() * 0.65
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
    urls = {
        Service.YOUTUBE: 'https://youtu.be/ABC',
        Service.INSTAGRAM: 'https://instagram.com/p/ABC/',
        Service.GETCOURSE: 'https://school.getcourse.ru/pl/teach/control/lesson/view?id=123',
    }
    job = Job(
        'color',
        DownloadRequest(parse_url(urls[service]), window.presenter.settings.presets[service]),
        state=JobState.DOWNLOADING,
    )
    window.presenter.repository.add(job)
    window.presenter.model.update_job(job, ProgressChanged(50, 100))
    qtbot.waitUntil(lambda: window.proxy.rowCount() == 1)
    window.queue_view.repaint()
    expected = QColor(window.theme.tokens()[service.value])
    image = window.queue_view.viewport().grab().toImage()
    dpr = image.devicePixelRatio()
    assert image.pixelColor(int(64 * dpr), int(72 * dpr)) == expected
    button = window.add_button.grab().toImage()
    actual = button.pixelColor(
        int((window.add_button.width() - 8) * button.devicePixelRatio()),
        int(window.add_button.height() / 2 * button.devicePixelRatio()),
    )
    difference = abs(actual.hueF() - expected.hueF())
    assert min(difference, 1 - difference) < 0.08


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
        assert (
            window.composer.add_button.width()
            >= window.composer.add_button.fontMetrics().horizontalAdvance(
                window.composer.add_button.text()
            )
            + 12
        )


@pytest.mark.parametrize('language', ['ru', 'en'])
@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_checked_mode_text_has_full_bold_content_width(make_window, qtbot, language, theme):
    from PySide6.QtWidgets import QStyle, QStyleOptionButton

    window, _ = make_window()
    window.language_actions[language].trigger()
    window.theme_actions[theme].trigger()
    window.resize(880, 680)
    for service in Service:
        window.composer.set_service(service)
        for mode, button in window.composer.mode_buttons.items():
            if mode == 'batch' or not button.isVisible():
                continue
            qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
            window.composer.layout().activate()
            option = QStyleOptionButton()
            button.initStyleOption(option)
            content = button.style().subElementRect(
                QStyle.SubElement.SE_PushButtonContents, option, button
            )
            text_width = button.fontMetrics().horizontalAdvance(button.text())
            assert content.width() >= text_width + 2, (
                service,
                mode,
                button.text(),
                content.width(),
                text_width,
            )


@pytest.mark.parametrize('section', ['accounts', 'settings'])
def test_batch_button_only_visible_in_download_sections(make_window, qtbot, section):
    window, _ = make_window()
    getattr(window, section + '_button').click()
    assert not window.batch_button.isVisible()
    window.nav_buttons[1].click()
    assert window.batch_button.isVisible()
    window.nav_buttons[0].click()
    assert window.batch_button.isVisible()


def test_mode_caption_yields_space_to_wide_control_metrics(make_window, qtbot):
    from PySide6.QtWidgets import QLabel

    window, _ = make_window()
    window.resize(880, 680)
    window.language_actions['en'].trigger()
    caption = next(
        label for label in window.composer.findChildren(QLabel) if label.text() == 'Download'
    )
    caption.setMinimumWidth(130)
    # Actual fallback-font widths observed on Windows offscreen, with safe ink padding.
    for name, width in [('single', 174), ('batch', 198), ('playlist', 126)]:
        window.composer.mode_buttons[name].setMinimumWidth(width)
    window.composer._arrange_entry()
    qtbot.waitUntil(
        lambda: (
            not caption.isVisible() and window.composer_host.horizontalScrollBar().maximum() == 0
        )
    )
    assert not caption.isVisible()
    assert all(
        window.composer.mode_buttons[name].isVisible() for name in ('single', 'batch', 'playlist')
    )


@pytest.mark.parametrize('mode', ['single', 'profile'])
def test_instagram_options_use_full_panel_height_without_inner_scroll(make_window, qtbot, mode):
    window, _ = make_window()
    window.resize(880, 680)
    window._navigate('instagram', False, 'Instagram')
    window.composer.mode_buttons[mode].click()
    window.composer.parameters_button.setChecked(True)
    qtbot.waitUntil(
        lambda: (
            window.composer_host.height() >= window.composer.sizeHint().height()
            and window.composer_host.verticalScrollBar().maximum() == 0
        )
    )
    folder_bottom = window.folder_input.mapTo(
        window.composer_host.viewport(), window.folder_input.rect().bottomRight()
    ).y()
    assert folder_bottom < window.composer_host.viewport().height()
    assert window.height() == 680
    assert window.queue_view.height() >= 96
