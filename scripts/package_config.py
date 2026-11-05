"""Shared PyInstaller inputs, independent of legacy source/."""

import os
import re
import runpy
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_VERSION = runpy.run_path(str(ROOT / 'src/clipflow/version.py'))['APP_VERSION']


def runtime_folder(system=None):
    system = sys.platform if system is None else system
    if system.startswith('linux'):
        return 'linux'
    try:
        return {'win32': 'windows', 'darwin': 'macos'}[system]
    except KeyError:
        raise ValueError('Unsupported platform: ' + system) from None


def resolve_tool(name):
    explicit = os.environ.get('CLIPFLOW_' + name.upper() + '_PATH')
    if explicit:
        path = Path(explicit)
        if not path.is_file():
            raise RuntimeError('Explicit tool is missing: ' + name)
        return path.resolve()
    executable = name + ('.exe' if os.name == 'nt' else '')
    for folder in (
        Path(os.environ.get('CLIPFLOW_BIN_DIR', 'nonexistent')),
        ROOT / '.runtime' / runtime_folder() / 'bin',
    ):
        candidate = folder / executable
        if candidate.is_file():
            return candidate.resolve()
    found = shutil.which(executable)
    if not found:
        raise RuntimeError(f'Required build tool missing: {name}')
    return Path(found).resolve()


def windows_build_environment(environment, python, base_prefix):
    system = Path(environment.get('SystemRoot') or environment['SYSTEMROOT'])
    paths = (
        Path(python).parent,
        Path(base_prefix),
        Path(base_prefix) / 'DLLs',
        system / 'System32',
        system,
    )
    return dict(environment, PATH=os.pathsep.join(dict.fromkeys(map(str, paths))))


def spec_inputs(root, system):
    from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

    root = Path(root)
    data = [(str(root / 'THIRD-PARTY-NOTICES.md'), 'licenses')]
    data += [(str(root / 'assets/icons/clipflow.png'), 'assets/icons')]
    data += [
        (str(path), 'licenses')
        for path in sorted((root / 'assets/licenses').glob('*'))
        if path.is_file()
    ]
    data += [
        (str(path), 'licenses') for path in sorted((root / 'work/package-licenses').glob('*.txt'))
    ]
    data += [(str(root / 'work/package-build-info.json'), '.')]
    for package in ('yt_dlp', 'yt_dlp_ejs'):
        data += collect_data_files(package, excludes=['**/*.py', '**/*.pyc', '**/__pycache__/**'])
    for package in (
        'yt-dlp',
        'yt-dlp-ejs',
        'PySide6',
        'instaloader',
        'cryptography',
        'keyring',
        'Pillow',
    ):
        data += copy_metadata(package, recursive=True)
    hidden = collect_submodules('yt_dlp') + collect_submodules('yt_dlp_ejs')
    hidden += [
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineWidgets',
        'clipflow.infrastructure.auth_process.__main__',
        'clipflow.infrastructure.auth_process.window',
    ]
    if system == 'linux':
        hidden += ['keyring.backends.SecretService']
        for package in ('SecretStorage', 'jeepney'):
            data += copy_metadata(package)
    if system == 'macos':
        hidden += ['keyring.backends.macOS']
    return dict(
        pathex=[str(root / 'src')],
        binaries=[(str(resolve_tool(name)), 'bin') for name in ('ffmpeg', 'ffprobe', 'node')],
        datas=data,
        hiddenimports=hidden,
        excludes=[
            'tkinter',
            '_tkinter',
            'customtkinter',
            'pytest',
            '_pytest',
            'coverage',
            'PySide6.Qt3DCore',
            'PySide6.QtCharts',
            'PySide6.QtDesigner',
            'PySide6.QtTest',
        ],
        noarchive=False,
    )


GLIBC_LIMIT = (2, 35)


def linux_arch(machine):
    try:
        return {'x86_64': 'x86_64', 'amd64': 'x86_64', 'arm64': 'aarch64', 'aarch64': 'aarch64'}[
            machine.lower()
        ]
    except KeyError:
        raise ValueError('Unsupported Linux architecture: ' + machine) from None


def linux_artifact_names(version, arch):
    arch = linux_arch(arch)
    prefix = f'ClipFlow-{version}-Linux-{arch}'
    return {'setup': prefix + '-Setup.run', 'portable': prefix + '-portable.tar.gz'}


def max_glibc(text):
    versions = [tuple(map(int, match)) for match in re.findall(r'GLIBC_(\d+)\.(\d+)', text)]
    return max(versions, default=None)


def glibc_violations(root, run=subprocess.run):
    violations = []
    for path in sorted(Path(root).rglob('*')):
        if not path.is_file():
            continue
        with path.open('rb') as stream:
            elf = stream.read(4) == b'\x7fELF'
        if not elf:
            continue
        result = run(['objdump', '-T', path], capture_output=True, text=True, check=True)
        version = max_glibc(result.stdout)
        if version and version > GLIBC_LIMIT:
            violations.append(str(path.relative_to(root)))
    return violations


def desktop_entry(exec_path, icon='clipflow'):
    if any(char in exec_path + icon for char in '\0\n\r'):
        raise ValueError('Invalid desktop entry')
    # Desktop value escaping is applied after the quoted Exec argument escaping.
    quoted = ''.join(('\\' + char) if char in '\\"`$' else char for char in exec_path)
    quoted = quoted.replace('\\', '\\\\').replace('%', '%%')
    return (
        '[Desktop Entry]\nType=Application\nName=ClipFlow\n'
        'Comment=Download your videos\nComment[ru]=Скачивание видео\n'
        f'Exec="{quoted}"\nIcon={icon}\nTerminal=false\n'
        'Categories=AudioVideo;Network;\nStartupWMClass=ClipFlow\n'
    )
