import os
import subprocess
import sys

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QKeySequence
from PySide6.QtWidgets import QApplication

from clipflow.domain.models import Service
from tests.support.clipboard import context_paste, paste_shortcut
from tests.support.workbench import batch


@pytest.mark.parametrize('method', ['shortcut', 'button', 'context'])
def test_ctrl_command_v_button_context_menu_all_services(make_window, qtbot, clipboard, method):
    window, _ = make_window()
    urls = {
        Service.YOUTUBE: 'https://youtu.be/ABC',
        Service.INSTAGRAM: 'https://instagram.com/p/POST/',
        Service.GETCOURSE: 'https://school.getcourse.ru/pl/teach/control/lesson/view?id=123',
    }
    for service, url in urls.items():
        window.composer.set_service(service)
        window.url_input.clear()
        clipboard.setText(url)
        if method == 'shortcut':
            paste_shortcut(qtbot, window.url_input)
        elif method == 'button':
            qtbot.mouseClick(window.composer.paste_button, Qt.MouseButton.LeftButton)
        else:
            context_paste(qtbot, window.url_input)
        assert window.url_input.text() == url
    dialog = batch(window, qtbot)
    clipboard.setText('\n'.join(urls.values()))
    paste_shortcut(qtbot, dialog.text_input)
    assert len(dialog.preview().requests) == 3


def test_russian_keyboard_edit_shortcuts(make_window, qtbot, clipboard):
    window, _ = make_window()
    field = window.url_input
    field.setText('draft')
    field.setFocus()
    modifier = QKeySequence(QKeySequence.StandardKey.Paste)[0].keyboardModifiers()

    def key(letter):
        QApplication.sendEvent(
            field, QKeyEvent(QKeyEvent.Type.KeyPress, ord(letter.upper()), modifier, letter)
        )

    key('ф')
    assert field.selectedText() == 'draft'
    key('с')
    assert clipboard.text() == 'draft'
    key('ч')
    assert field.text() == ''
    key('м')
    assert field.text() == 'draft'
    key('я')
    assert field.text() == ''
    key('н')
    assert field.text() == 'draft'


def test_batch_shortcut_ctrl_command_n(make_window, qtbot):
    window, _ = make_window()
    window.activateWindow()
    window.url_input.setFocus()
    qtbot.waitUntil(
        lambda: (
            QApplication.activeWindow() is window
            and QApplication.instance().applicationState() == Qt.ApplicationState.ApplicationActive
        )
    )
    qtbot.keySequence(window.url_input, QKeySequence(QKeySequence.StandardKey.New))
    qtbot.waitUntil(lambda: bool(window._dialogs))
    assert window._dialogs[-1].isVisible()


@pytest.mark.native_gui
def test_native_clipboard_roundtrip(make_window, qtbot, clipboard, qapp):
    if os.environ.get('CLIPFLOW_NATIVE_QA') != '1':
        pytest.skip('Run separately with CLIPFLOW_NATIVE_QA=1 in a native GUI session')
    assert qapp.platformName() in {'windows', 'cocoa'}, (
        'Offscreen is not native clipboard acceptance'
    )
    window, _ = make_window()
    clipboard.setText('https://youtu.be/NATIVE')
    paste_shortcut(qtbot, window.url_input)
    assert window.url_input.text() == 'https://youtu.be/NATIVE'
    window.url_input.clear()
    context_paste(qtbot, window.url_input)
    assert window.url_input.text() == 'https://youtu.be/NATIVE'


@pytest.mark.parametrize('scale', ['1', '1.5', '2'])
def test_separate_process_dpi(scale, tmp_path, qapp):
    from pathlib import Path

    base = qapp.primaryScreen().devicePixelRatio() / float(os.environ.get('QT_SCALE_FACTOR', '1'))
    env = dict(
        os.environ,
        QT_SCALE_FACTOR=scale,
        CLIPFLOW_BASE_DPR=str(base),
        CLIPFLOW_DATA_DIR=str(tmp_path / 'dpi'),
    )
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name('qt_dpi_probe.py'))],
        env=env,
        capture_output=True,
        text=True,
        timeout=40,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f'PASS DPI {scale}' in result.stdout
