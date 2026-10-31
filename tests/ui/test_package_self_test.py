import os
import subprocess
import sys

import pytest


def test_ui_self_test_isolated_and_reports_real_local_transfer(tmp_path):
    import json

    report = tmp_path / 'report.json'
    data = tmp_path / 'data'
    result = subprocess.run(
        [
            sys.executable,
            '-m',
            'clipflow',
            '--ui-self-test',
            '--data-dir',
            str(data),
            '--report',
            str(report),
        ],
        env=dict(os.environ, CLIPFLOW_DATA_DIR=str(tmp_path)),
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    proof = json.loads(report.read_text(encoding='utf-8'))
    assert proof['passed'] and proof['ui'] == 'qt' and proof['local_transfer']
    assert proof['worker_idle'] and not proof['legacy_modules']
    from clipflow.version import APP_VERSION

    assert proof['version'] == APP_VERSION and (data / 'ui.png').is_file()


def test_ui_self_test_refuses_unisolated_storage(tmp_path):
    env = dict(os.environ)
    env.pop('CLIPFLOW_DATA_DIR', None)
    fake = str(tmp_path / 'fake-home')
    env.update(HOME=fake, USERPROFILE=fake, LOCALAPPDATA=str(tmp_path / 'fake-local'))
    try:
        result = subprocess.run(
            [
                sys.executable,
                '-m',
                'clipflow',
                '--ui-self-test',
                '--data-dir',
                str(tmp_path),
                '--report',
                str(tmp_path / 'report.json'),
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except subprocess.TimeoutExpired:
        pytest.fail('Self-test CLI opened a main window instead of refusing unisolated storage')
    assert result.returncode == 2 and not (tmp_path / 'queue.sqlite3').exists()
