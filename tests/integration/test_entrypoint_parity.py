"""Release entrypoints exercise the same real Qt/self-test implementation."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_default_entrypoint_is_qt(tmp_path):
    report = tmp_path / 'report.json'
    result = subprocess.run(
        [
            sys.executable,
            'run.py',
            '--ui-self-test',
            '--data-dir',
            str(tmp_path / 'data'),
            '--report',
            str(report),
        ],
        cwd=ROOT,
        env=dict(os.environ, CLIPFLOW_DATA_DIR=str(tmp_path)),
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert report.is_file(), 'Default entry still invokes legacy UI rather than Qt self-test'
    proof = json.loads(report.read_text(encoding='utf-8'))
    assert proof['passed'] and proof['ui'] == 'qt' and proof['local_transfer']


def test_no_ast_test_extraction():
    pattern = re.compile(r'exec\s*\(\s*compile\s*\(\s*ast[.]Module')
    bad = [
        str(p.relative_to(ROOT))
        for p in (ROOT / 'tests').rglob('*.py')
        if pattern.search(p.read_text(encoding='utf-8-sig'))
    ]
    assert not bad, f'Production functions extracted into fake test namespaces: {bad}'


def test_no_tk_import_in_supported_runtime(tmp_path):
    arguments = [
        'run.py',
        '--ui-self-test',
        '--data-dir',
        str(tmp_path / 'data'),
        '--report',
        str(tmp_path / 'report.json'),
    ]
    code = f"""import runpy,sys
sys.argv={arguments!r}
try: runpy.run_path('run.py',run_name='__main__')
except SystemExit as result: assert result.code in (0,None)
assert 'clipflow.ui.bootstrap' in sys.modules
assert not any(name in sys.modules for name in ('tkinter','_tkinter','customtkinter'))
"""
    result = subprocess.run(
        [sys.executable, '-c', code],
        cwd=ROOT,
        env=dict(os.environ, CLIPFLOW_DATA_DIR=str(tmp_path)),
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_legacy_parity_matrix_has_real_test_targets():
    mapping = json.loads((ROOT / 'tests/legacy-parity.json').read_text(encoding='utf-8'))
    assert len(mapping) == 11
    for legacy, targets in mapping.items():
        assert legacy.startswith('test_') and targets
        for target in targets:
            path, function = target.split('::')
            source = ROOT / path
            assert source.is_file() and f'def {function}(' in source.read_text(encoding='utf-8')
