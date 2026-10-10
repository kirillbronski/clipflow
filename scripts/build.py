"""Build native installers from the single shared ClipFlow source tree."""
from pathlib import Path
import argparse
import os
import platform
import runpy
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
VERSION = runpy.run_path(str(ROOT / 'source/version.py'))['APP_VERSION']

def run(*args, **kwargs):
    subprocess.run([str(arg) for arg in args], cwd=ROOT, check=True, **kwargs)

def check_auth(executable):
    for flag, service in [('--auth-self-test', 'youtube'), ('--instagram-auth-self-test', 'instagram')]:
        directory = ROOT / 'work' / 'build-verification' / service
        env = dict(os.environ, CLIPFLOW_DATA_DIR=str(directory))
        run(executable, flag, directory, env=env, timeout=90)

def macos():
    if platform.machine() != 'arm64':
        raise SystemExit('The current macOS release targets Apple Silicon (arm64).')
    run(sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--distpath', ROOT/'outputs',
        '--workpath', ROOT/'work/build', ROOT/'packaging/macos/ClipFlow.spec')
    app = ROOT/'outputs/ClipFlow.app'
    run('codesign', '--verify', '--deep', '--strict', app)
    check_auth(app/'Contents/MacOS/ClipFlow')
    # App copies only exist while staging the DMG, keeping Launchpad clean.
    stage = ROOT/'work/dmg'
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    try:
        run('ditto', app, stage/'ClipFlow.app')
        (stage/'Applications').symlink_to('/Applications')
        shutil.copy2(ROOT/'INSTALL.txt', stage)
        image = ROOT/'outputs'/f'ClipFlow-{VERSION}-macOS-arm64.dmg'
        run('hdiutil', 'create', '-volname', f'ClipFlow {VERSION}', '-srcfolder', stage, '-ov', '-format', 'UDZO', image)
        run('hdiutil', 'verify', image)
        run('ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', app,
            ROOT/'outputs'/f'ClipFlow-{VERSION}-macOS-app.zip')
    finally:
        ls = '/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister'
        subprocess.run([ls, '-u', str(stage/'ClipFlow.app')], capture_output=True)
        shutil.rmtree(stage)
    print('Release ready:', image)

def windows(portable_only=False):
    from importlib.util import find_spec
    if find_spec('PyInstaller') is None:
        raise SystemExit('Install requirements.txt into this Python environment first.')
    sys.path.insert(0, str(ROOT/'source'))
    from platform_support import binary_path
    args = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed', '--onedir',
            '--name', 'ClipFlow', '--icon', str(ROOT/'assets/icons/clipflow.ico'),
            '--distpath', str(ROOT/'outputs'), '--workpath', str(ROOT/'work/build'),
            '--specpath', str(ROOT/'work'), '--paths', str(ROOT/'source'),
            '--paths', str(ROOT/'source/_internal')]
    for name in ['clipflow.png', 'clipflow-getcourse.png', 'clipflow-instagram.png']:
        args += ['--add-data', str(ROOT/'source'/name)+os.pathsep+'.']
    args += ['--add-data', str(ROOT/'assets/licenses/Instaloader-LICENSE.txt')+os.pathsep+'licenses']
    for package in ['yt_dlp', 'yt_dlp_ejs']:
        args += ['--collect-submodules', package, '--collect-data', package]
    args += ['--collect-data', 'customtkinter', '--hidden-import', 'PySide6.QtWebEngineCore',
             '--hidden-import', 'PySide6.QtWebEngineWidgets']
    for name in ['ffmpeg','ffprobe','node']:
        binary = binary_path(name)
        if not binary:
            raise SystemExit(f'{name} missing. Add it to PATH or set CLIPFLOW_BIN_DIR.')
        args += ['--add-binary', binary+os.pathsep+'bin']
    args += [str(ROOT/'source/clipflow.py')]
    # PyInstaller builds into a new directory; existing installers remain untouched.
    distribution = ROOT/'outputs/ClipFlow'
    if distribution.exists():
        shutil.rmtree(distribution)
    run(*args)
    check_auth(distribution/'ClipFlow.exe')
    archive = shutil.make_archive(str(ROOT/'outputs'/f'ClipFlow-{VERSION}-Windows-x64-portable'), 'zip',
                                  ROOT/'outputs', 'ClipFlow')
    if not portable_only:
        compiler = os.environ.get('INNO_SETUP_COMPILER') or shutil.which('ISCC')
        if not compiler:
            candidates = [Path(os.environ.get(key,''))/'Inno Setup 6/ISCC.exe' for key in ['ProgramFiles(x86)','ProgramFiles']]
            compiler = next((str(p) for p in candidates if p.is_file()), None)
        if not compiler:
            raise SystemExit('Portable ZIP built. Install Inno Setup 6 for the installer, or use --portable-only.')
        run(compiler, '/DAppVersion='+VERSION, ROOT/'packaging/windows/setup.iss')
    print('Portable release ready:', archive)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--portable-only', action='store_true', help='Windows: skip Inno Setup installer')
    options = parser.parse_args()
    (ROOT/'outputs').mkdir(exist_ok=True)
    if sys.platform == 'darwin':
        macos()
    elif sys.platform == 'win32':
        windows(options.portable_only)
    else:
        parser.error('Native builds require Windows or macOS.')
