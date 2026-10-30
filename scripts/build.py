"""Native Qt candidates; fresh stages, bundled-tool smoke, source provenance."""

from pathlib import Path
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from urllib.request import urlopen
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
from package_config import APP_VERSION, spec_inputs, resolve_tool, windows_build_environment


def run(*args, **kwargs):
    return subprocess.run([str(v) for v in args], cwd=ROOT, check=True, **kwargs)


def prepare():
    directory = ROOT / 'work/package-licenses'
    directory.mkdir(parents=True, exist_ok=True)
    node = run(resolve_tool('node'), '--version', capture_output=True, text=True).stdout.strip()
    if not node.startswith('v') or not all(c.isdigit() or c in '.v' for c in node):
        raise RuntimeError('Invalid Node version')
    license = directory / f'Node-{node}-LICENSE.txt'
    if not license.exists():
        with urlopen(
            f'https://raw.githubusercontent.com/nodejs/node/{node}/LICENSE', timeout=30
        ) as response:
            license.write_bytes(response.read())
    digest = hashlib.sha256()
    paths = (
        list((ROOT / 'src/clipflow').rglob('*.py'))
        + list((ROOT / 'scripts').glob('*.py'))
        + list((ROOT / 'packaging').rglob('*'))
    )
    for path in sorted(p for p in paths if p.is_file() and '__pycache__' not in p.parts):
        digest.update(str(path.relative_to(ROOT)).replace('\\', '/').encode())
        digest.update(path.read_bytes())
    info = {
        'version': APP_VERSION,
        'source_commit': run(
            'git', 'rev-parse', 'HEAD', capture_output=True, text=True
        ).stdout.strip(),
        'dirty': bool(
            run('git', 'status', '--porcelain', capture_output=True, text=True).stdout.strip()
        ),
        'source_fingerprint': digest.hexdigest(),
        'os': platform.platform(),
        'cpu': platform.machine(),
        'built_at_utc': datetime.now(timezone.utc).isoformat(),
        'channel': 'candidate',
    }
    (ROOT / 'work/package-build-info.json').write_text(
        json.dumps(info, indent=2) + '\n', encoding='utf-8'
    )
    numbers = tuple(map(int, APP_VERSION.split('.'))) + (0,)
    version = f"""VSVersionInfo(ffi=FixedFileInfo(filevers={numbers!r},prodvers={numbers!r},
mask=0x3f,flags=0x0,OS=0x40004,fileType=0x1,subtype=0x0,date=(0,0)),kids=[
StringFileInfo([StringTable('040904B0',[
StringStruct('FileVersion',{APP_VERSION!r}),StringStruct('ProductVersion',{APP_VERSION!r}),
StringStruct('ProductName','ClipFlow'),StringStruct('FileDescription','ClipFlow'),
StringStruct('OriginalFilename','ClipFlow.exe')])]),VarFileInfo([VarStruct('Translation',[1033,1200])])])"""
    (ROOT / 'work/windows-version.txt').write_text(version, encoding='utf-8')
    return info


def installer_compiler():
    candidates = [os.environ.get('INNO_SETUP_COMPILER'), shutil.which('ISCC')]
    candidates += [
        str(Path(os.environ.get(key, '')) / 'Inno Setup 6/ISCC.exe')
        for key in ('ProgramFiles(x86)', 'ProgramFiles')
    ]
    result = next((p for p in candidates if p and Path(p).is_file()), None)
    if result is None:
        raise RuntimeError(
            'Set INNO_SETUP_COMPILER or install Inno Setup 6; --portable-only skips installer'
        )
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--portable-only', action='store_true')
    parser.add_argument('--skip-smoke', action='store_true')
    args = parser.parse_args(argv)
    system = 'windows' if sys.platform == 'win32' else 'macos' if sys.platform == 'darwin' else None
    if system is None:
        parser.error('Build on native Windows or macOS')
    if system == 'macos' and platform.machine() != 'arm64':
        parser.error('macOS release targets Apple Silicon arm64')
    info = prepare()
    label = system + '-' + uuid4().hex[:10]
    output = ROOT / 'outputs' / APP_VERSION / label
    output.mkdir(parents=True, exist_ok=False)
    stage = ROOT / 'work/native-build' / label
    stage.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ)
    env.update(
        {
            'CLIPFLOW_' + name.upper() + '_PATH': str(resolve_tool(name))
            for name in ('ffmpeg', 'ffprobe', 'node')
        }
    )
    if system == 'windows':
        env = windows_build_environment(env, Path(sys.executable), Path(sys.base_prefix))
    run(
        sys.executable,
        '-m',
        'PyInstaller',
        '--noconfirm',
        '--clean',
        '--distpath',
        output,
        '--workpath',
        stage,
        ROOT / f'packaging/{system}/ClipFlow.spec',
        env=env,
    )
    app = output / ('ClipFlow' if system == 'windows' else 'ClipFlow.app')
    executable = app / ('ClipFlow.exe' if system == 'windows' else 'Contents/MacOS/ClipFlow')
    if system == 'macos':
        run('codesign', '--verify', '--deep', '--strict', app)
    if not args.skip_smoke:
        smoke = ROOT / 'work/package-smoke' / label
        run(
            sys.executable,
            ROOT / 'scripts/package_smoke.py',
            '--executable',
            executable,
            '--data-dir',
            smoke,
            timeout=240,
        )
        shutil.copy2(smoke / 'package-report.json', output / 'package-report.json')
    artifacts = []
    if system == 'windows':
        archive = shutil.make_archive(
            str(output / f'ClipFlow-{APP_VERSION}-Windows-x64-portable'), 'zip', output, 'ClipFlow'
        )
        artifacts.append(Path(archive))
        if not args.portable_only:
            run(
                installer_compiler(),
                '/DAppVersion=' + APP_VERSION,
                '/DDistributionRoot=' + str(app),
                '/DOutputRoot=' + str(output),
                ROOT / 'packaging/windows/setup.iss',
            )
            artifacts.append(output / f'ClipFlow-Setup-{APP_VERSION}.exe')
    else:
        dmg_stage = stage / 'dmg'
        dmg_stage.mkdir()
        run('ditto', app, dmg_stage / 'ClipFlow.app')
        (dmg_stage / 'Applications').symlink_to('/Applications')
        shutil.copy2(ROOT / 'INSTALL.txt', dmg_stage)
        image = output / f'ClipFlow-{APP_VERSION}-macOS-arm64.dmg'
        try:
            run(
                'hdiutil',
                'create',
                '-volname',
                f'ClipFlow {APP_VERSION}',
                '-srcfolder',
                dmg_stage,
                '-ov',
                '-format',
                'UDZO',
                image,
            )
            run('hdiutil', 'verify', image)
            archive = output / f'ClipFlow-{APP_VERSION}-macOS-app.zip'
            run('ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', app, archive)
            artifacts += [image, archive]
        finally:
            ls = '/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister'
            subprocess.run([ls, '-u', str(dmg_stage / 'ClipFlow.app')], capture_output=True)
            shutil.rmtree(dmg_stage)
    info['artifacts'] = [
        {
            'name': path.name,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'bytes': path.stat().st_size,
        }
        for path in artifacts
    ]
    info['package_smoke'] = not args.skip_smoke
    info['launch_services_mac27_verified'] = False
    (output / 'build-report.json').write_text(json.dumps(info, indent=2) + '\n', encoding='utf-8')
    (output / 'SHA256SUMS.txt').write_text(
        ''.join(a['sha256'] + '  ' + a['name'] + '\n' for a in info['artifacts']), encoding='utf-8'
    )
    print('Native candidate ready:', output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
