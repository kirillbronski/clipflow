"""The row menu as in 4K, behind «⋮» and the right click alike."""

import sys
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtCore import QItemSelectionModel
from PySide6.QtGui import QDesktopServices

from clipflow.domain.models import (
    ContentKind,
    DownloadOptions,
    DownloadRequest,
    Job,
    JobState,
    ParsedLink,
    Service,
)
from clipflow.domain.urls import parse_url
from clipflow.infrastructure.repository import SqliteJobRepository

PLAYLIST = 'https://www.youtube.com/playlist?list=PLgroup'


def seeded(make_window, tmp_path, *jobs):
    repo = SqliteJobRepository(tmp_path / 'menu.sqlite3')
    for job in jobs:
        repo.add(job)
    window, _ = make_window(repository=repo)
    return window


def job(identity, state=JobState.QUEUED, files=(), url=None, parent=None):
    folder = files[0].parent if files else Path('/d')
    request = DownloadRequest(
        parse_url(url or f'https://youtu.be/{identity}'), DownloadOptions(folder)
    )
    return Job(identity, request, state=state, result_files=files, parent_id=parent)


def texts(menu):
    return [(a.text(), a.isEnabled()) for a in menu.actions() if not a.isSeparator()]


def action(window, menu, key):
    text = window.tr.text(key)
    return next(a for a in menu.actions() if a.text() == text)


def reveal_key():
    return 'row_menu.reveal' if sys.platform == 'darwin' else 'row_menu.reveal_windows'


@pytest.mark.parametrize(
    ('state', 'files', 'enabled'),
    [
        (JobState.QUEUED, False, {'copy', 'open', 'cancel'}),
        (JobState.FAILED, False, {'copy', 'open', 'repeat', 'remove'}),
        (JobState.COMPLETED, True, {'reveal', 'copy', 'open', 'repeat', 'remove', 'delete'}),
    ],
)
def test_row_menu_items_and_enabled_state(make_window, tmp_path, state, files, enabled):
    paths = ()
    if files:
        target = tmp_path / 'a.mp4'
        target.write_bytes(b'x')
        paths = (target,)
    window = seeded(make_window, tmp_path, job('abc', state, paths))
    menu = window.dialogs.row_menu('abc')
    keys = {
        'reveal': reveal_key(),
        'copy': 'row_menu.copy_link',
        'open': 'row_menu.open_link',
        'repeat': 'row_menu.repeat',
        'cancel': 'row_menu.cancel',
        'remove': 'remove_list',
        'delete': 'delete_files',
    }
    assert [text for text, _ in texts(menu)] == [window.tr.text(keys[k]) for k in keys]
    assert {k for k in keys if action(window, menu, keys[k]).isEnabled()} == enabled
    menu.close()


def test_copy_link_puts_url_on_clipboard(make_window, tmp_path, clipboard):
    window = seeded(make_window, tmp_path, job('abc'))
    menu = window.dialogs.row_menu('abc')
    action(window, menu, 'row_menu.copy_link').trigger()
    assert clipboard.text() == 'https://www.youtube.com/watch?v=abc'
    menu.close()


def test_open_link_uses_desktop_services(make_window, tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr(QDesktopServices, 'openUrl', lambda url: opened.append(url.toString()))
    window = seeded(make_window, tmp_path, job('abc'))
    menu = window.dialogs.row_menu('abc')
    action(window, menu, 'row_menu.open_link').trigger()
    assert opened == ['https://www.youtube.com/watch?v=abc']
    menu.close()


def test_cancel_from_menu_cancels(make_window, tmp_path, qtbot):
    window = seeded(make_window, tmp_path, job('abc'))
    window.presenter.toggle_job('abc')
    qtbot.waitUntil(lambda: window.presenter.repository.get('abc').state == JobState.DOWNLOADING)
    menu = window.dialogs.row_menu('abc')
    action(window, menu, 'row_menu.cancel').trigger()
    qtbot.waitUntil(lambda: window.presenter.executor.is_idle)
    assert window.presenter.repository.get('abc').state == JobState.CANCELLED


def test_menu_button_opens_the_row_menu(make_window, tmp_path, monkeypatch):
    window = seeded(make_window, tmp_path, job('abc'))
    opened = []
    monkeypatch.setattr(window.dialogs, 'row_menu', lambda identity: opened.append(identity))
    window._row_action('abc', 'row_menu')
    assert opened == ['abc']


def test_menu_acts_on_selection(make_window, tmp_path, monkeypatch, clipboard):
    window = seeded(make_window, tmp_path, job('one', JobState.FAILED), job('two', JobState.FAILED))
    view = window.queue_view
    flags = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
    for row in range(2):
        view.selectionModel().select(window.proxy.index(row, 0), flags)
    target = window.proxy.index(1, 0).data(window.presenter.model.JobIdRole)
    menu = window.dialogs.row_menu(target)
    action(window, menu, 'row_menu.copy_link').trigger()
    assert clipboard.text().endswith('v=' + target)
    removed = []
    monkeypatch.setattr(window.presenter, 'remove_jobs', removed.append)
    action(window, menu, 'remove_list').trigger()
    assert sorted(removed[0]) == ['one', 'two']
    menu.close()


def test_protected_link_cannot_be_copied(make_window, tmp_path):
    link = ParsedLink(
        Service.GETCOURSE, ContentKind.LESSON, 'protected-' + 'a' * 64, 'https://school.example/'
    )
    secret = Job(
        'secret',
        DownloadRequest(link, DownloadOptions(tmp_path)),
        state=JobState.FAILED,
        source_required=True,
    )
    window = seeded(make_window, tmp_path, secret)
    menu = window.dialogs.row_menu('secret')
    assert not action(window, menu, 'row_menu.copy_link').isEnabled()
    assert not action(window, menu, 'row_menu.open_link').isEnabled()
    menu.close()


def test_group_menu_has_link_items(make_window, tmp_path, monkeypatch, clipboard):
    opened = []
    monkeypatch.setattr(QDesktopServices, 'openUrl', lambda url: opened.append(url.toString()))
    parent = job('p', JobState.COMPLETED, url=PLAYLIST)
    window = seeded(make_window, tmp_path, parent, replace(job('c'), parent_id='p'))
    menu = window.dialogs.group_menu('p')
    action(window, menu, 'row_menu.copy_link').trigger()
    assert clipboard.text() == parent.request.link.canonical_url
    action(window, menu, 'row_menu.open_link').trigger()
    assert opened == [parent.request.link.canonical_url]
    menu.close()


@pytest.mark.parametrize(
    ('platform', 'text'), [('darwin', 'Показать в Finder'), ('win32', 'Показать в Проводнике')]
)
def test_reveal_label_follows_platform(make_window, tmp_path, monkeypatch, platform, text):
    window = seeded(make_window, tmp_path, job('abc'))
    monkeypatch.setattr(sys, 'platform', platform)
    menu = window.dialogs.row_menu('abc')
    assert menu.actions()[0].text() == text
    menu.close()
