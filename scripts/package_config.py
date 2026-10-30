"""Shared PyInstaller inputs, independent of legacy source/."""

from pathlib import Path
import os
import runpy
import shutil

ROOT = Path(__file__).resolve().parents[1]
APP_VERSION = runpy.run_path(str(ROOT / 'src/clipflow/version.py'))['APP_VERSION']


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
        ROOT / '.runtime' / ('windows' if os.name == 'nt' else 'macos') / 'bin',
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
