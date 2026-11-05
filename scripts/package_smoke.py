"""Exercise the actual frozen distribution without the checkout, venv or user profiles."""

import argparse
import hashlib
import json
import os
import platform
import subprocess
from pathlib import Path


def clean_environment(data):
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(('PYTHON', 'CONDA', 'QT_', 'QTWEBENGINE', 'PYSIDE'))
        and key not in {'VIRTUAL_ENV', 'DYLD_LIBRARY_PATH', 'LD_LIBRARY_PATH'}
    }
    if os.name == 'nt':
        system = Path(env.get('SystemRoot') or env['SYSTEMROOT'])
        env['PATH'] = os.pathsep.join(map(str, (system / 'System32', system)))
    else:
        env['PATH'] = '/usr/bin:/bin:/usr/sbin:/sbin'
    env.update(
        PYTHONNOUSERSITE='1',
        CLIPFLOW_DATA_DIR=str(data),
        QT_QPA_PLATFORM='windows' if os.name == 'nt' else 'cocoa',
    )
    return env


def inspect_package(executable):
    from PyInstaller.archive.readers import CArchiveReader

    root = executable.parent if os.name == 'nt' else executable.parents[2]
    files = [p for p in root.rglob('*') if p.is_file()]
    bad = [
        str(p.relative_to(root))
        for p in files
        if p.suffix.lower() in {'.py', '.pyc', '.pyo', '.spec', '.log'}
        or p.name
        in {
            'session.dat',
            'settings-v2.json',
            'settings.json',
            'queue.sqlite3',
            'getcourse-profile.dat',
        }
        or any(
            part in {'.venv', '__pycache__', 'customtkinter', '_tcl_data', '_tk_data'}
            for part in p.parts
        )
    ]
    if bad:
        raise RuntimeError('Unexpected source/profile files: ' + ', '.join(bad[:5]))
    if any(not p.resolve().is_relative_to(root.resolve()) for p in files):
        raise RuntimeError('External bundle symlink')
    archive = CArchiveReader(str(executable))
    pyz = archive.open_embedded_archive('PYZ.pyz')
    modules = tuple(pyz.toc)
    if any(
        name.split('.')[0]
        in {'tkinter', '_tkinter', 'customtkinter', 'platform_support', 'embedded_auth'}
        for name in modules
    ):
        raise RuntimeError('Legacy runtime in frozen archive')
    if (
        'clipflow.ui.bootstrap' not in modules
        or 'clipflow.infrastructure.auth_process.window' not in modules
    ):
        raise RuntimeError('Missing Qt/auth modules')
    names = {p.name for p in files}
    for required in ('qtwebengine_resources.pak', 'icudtl.dat', 'en-US.pak'):
        if required not in names:
            raise RuntimeError('Missing WebEngine resource: ' + required)
    if not any(name.startswith('QtWebEngineProcess') for name in names):
        raise RuntimeError('Missing WebEngine helper')
    if not any(p.name == 'THIRD-PARTY-NOTICES.md' for p in files):
        raise RuntimeError('Missing notices')
    return root, files


def run(executable, data):
    executable = Path(executable).resolve()
    data = Path(data).resolve()
    root, files = inspect_package(executable)
    if data.is_relative_to(root) or (data.exists() and any(data.iterdir())):
        raise RuntimeError('Smoke data must be fresh and outside the package')
    data.mkdir(parents=True, exist_ok=True)
    env = clean_environment(data)
    proof = {
        'passed': False,
        'os': platform.platform(),
        'cpu': platform.machine(),
        'executable_sha256': hashlib.sha256(executable.read_bytes()).hexdigest(),
        'file_count': len(files),
        'isolated': True,
        'venv_free': True,
        'tests': {},
    }
    for name in ('ffmpeg', 'ffprobe', 'node'):
        tool = next(
            (
                p
                for p in files
                if p.name.lower() == name + ('.exe' if os.name == 'nt' else '')
                and p.parent.name == 'bin'
            ),
            None,
        )
        if not tool:
            raise RuntimeError('Missing embedded tool: ' + name)
        result = subprocess.run(
            [str(tool), '--version' if name == 'node' else '-version'],
            env=env,
            cwd=data,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode:
            raise RuntimeError('Embedded tool failed: ' + name)
        proof['tests'][name] = {'passed': True, 'version': result.stdout.splitlines()[0]}
    for name, flag in (
        ('ui', '--ui-self-test'),
        ('youtube', '--auth-self-test'),
        ('instagram', '--instagram-auth-self-test'),
    ):
        directory = data / name
        directory.mkdir()
        report = directory / 'report.json'
        command = [str(executable), flag, '--data-dir', str(directory), '--report', str(report)]
        if name == 'ui':
            command += ['--require-frozen']
        result = subprocess.run(
            command, cwd=data, env=env, capture_output=True, text=True, timeout=60
        )
        if result.returncode or not report.is_file():
            if report.is_file():
                print('Self-test proof:', report.read_text(encoding='utf-8'))
            raise RuntimeError(
                f'Frozen {name} test failed: exit={result.returncode}; {result.stderr[-1500:]}'
            )
        result = json.loads(report.read_text(encoding='utf-8'))
        if not result.get('passed') or not result.get('frozen'):
            raise RuntimeError('Invalid frozen proof: ' + name)
        proof['tests'][name] = result
    proof['passed'] = True
    (data / 'package-report.json').write_text(
        json.dumps(proof, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
    )
    print(
        'PASS frozen Qt UI, local media/FFmpeg, both protected WebEngine self-tests, '
        'clean resources; ' + proof['os'] + ' ' + proof['cpu']
    )
    return proof


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', required=True)
    parser.add_argument('--data-dir', required=True)
    args = parser.parse_args(argv)
    run(args.executable, args.data_dir)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
