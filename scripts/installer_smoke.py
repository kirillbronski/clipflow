"""Install, update and remove a real QtIFW package in an isolated, unusual path."""

import argparse
import json
import os
import shlex
import subprocess
from pathlib import Path

import package_smoke


def desktop_executable(path):
    line = next(line[5:] for line in path.read_text().splitlines() if line.startswith('Exec='))
    # Desktop string escapes are decoded before Exec quoting.
    return Path(shlex.split(line.replace('\\\\', '\\'))[0].replace('%%', '%'))


def run(installer, work):
    work = Path(work).resolve()
    work.mkdir(parents=True, exist_ok=False)
    target = work / 'a b/кирилл/ClipFlow'
    xdg = work / 'xdg'
    data = xdg / 'ClipFlow'
    data.mkdir(parents=True)
    marker = data / 'profile-preserved'
    marker.write_text('synthetic-profile', encoding='utf-8')
    env = dict(
        os.environ, QT_QPA_PLATFORM='minimal', XDG_DATA_HOME=str(xdg), CLIPFLOW_DATA_DIR=str(data)
    )
    command = [
        str(Path(installer).resolve()),
        '--root',
        str(target),
        '--accept-licenses',
        '--default-answer',
        '--confirm-command',
        'install',
    ]
    for attempt in range(2):
        args = command + ([f'ClipFlowUpgradeTarget={target}'] if attempt else [])
        subprocess.run(args, env=env, check=True, timeout=180)
        desktop = xdg / 'applications/clipflow.desktop'
        if not desktop.is_file() or desktop_executable(desktop) != target / 'ClipFlow':
            raise RuntimeError('Installed desktop entry has an incorrect executable')
        if not (xdg / 'icons/hicolor/256x256/apps/clipflow.png').is_file():
            raise RuntimeError('Installed icon is missing')
        if marker.read_text() != 'synthetic-profile':
            raise RuntimeError('Installation changed the profile')
        package_smoke.run(target / 'ClipFlow', work / f'package-smoke-{attempt}')
    subprocess.run(
        [str(target / 'maintenancetool'), '--confirm-command', 'purge'],
        env=env,
        check=True,
        timeout=180,
    )
    if any((target / name).exists() for name in ('ClipFlow', 'maintenancetool')):
        raise RuntimeError('Uninstallation left program files')
    if any(
        (xdg / 'applications' / name).exists()
        for name in ('clipflow.desktop', 'clipflow-uninstall.desktop')
    ):
        raise RuntimeError('Uninstallation left desktop entries')
    if marker.read_text() != 'synthetic-profile':
        raise RuntimeError('Uninstallation changed the profile')
    (work / 'installer-report.json').write_text(
        json.dumps(
            {
                'passed': True,
                'install': True,
                'update': True,
                'uninstall': True,
                'profile_preserved': True,
            },
            indent=2,
        )
        + '\n'
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installer', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    run(args.installer, args.work)


if __name__ == '__main__':
    main()
