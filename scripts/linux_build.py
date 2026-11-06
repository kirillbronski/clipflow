"""Linux portable archive and per-user QtIFW installer, from a fresh native stage."""

import os
import shutil
import subprocess
import sys
import tarfile
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

from package_config import APP_VERSION, glibc_violations, linux_artifact_names, linux_glibc_limit


def installer_creator():
    creator = os.environ.get('QTIFW_BINARYCREATOR') or shutil.which('binarycreator')
    if not creator or not Path(creator).is_file():
        raise RuntimeError(
            'Set QTIFW_BINARYCREATOR or install Qt Installer Framework 4; '
            '--portable-only skips installer'
        )
    return creator


def installer_stage(root, stage, app):
    from PIL import Image

    directory = stage / 'installer'
    shutil.copytree(root / 'packaging/linux/installer', directory)
    data = directory / 'packages/com.clipflow.app/data'
    shutil.copytree(app, data)
    shutil.copy2(directory / 'packages/com.clipflow.app/meta/clipflow-uninstall.svg', data)
    (data / 'clipflow-install.txt').write_text(APP_VERSION + '\n', encoding='utf-8')
    with Image.open(root / 'assets/icons/clipflow.png') as icon:
        icon.resize((256, 256)).save(data / 'clipflow.png')
        icon.resize((256, 256)).save(directory / 'config/clipflow.png')
    for path in (
        directory / 'config/config.xml',
        directory / 'packages/com.clipflow.app/meta/package.xml',
    ):
        tree = ET.parse(path)
        tree.getroot().find('Version').text = APP_VERSION
        released = tree.getroot().find('ReleaseDate')
        if released is not None:
            released.text = date.today().isoformat()
        tree.write(path, encoding='utf-8', xml_declaration=True)
    return directory


def check_glibc(app, arch):
    limit = linux_glibc_limit(arch)
    violations = glibc_violations(app, limit=limit)
    if violations:
        raise RuntimeError(
            f'Package requires glibc newer than {limit[0]}.{limit[1]}: ' + ', '.join(violations)
        )


def build_artifacts(root, output, stage, app, arch, *, portable_only=False, skip_smoke=False):
    names = linux_artifact_names(APP_VERSION, arch)
    archive = output / names['portable']
    with tarfile.open(archive, 'w:gz') as stream:
        stream.add(app, arcname='ClipFlow')
    shutil.copy2(root / 'INSTALL.txt', output / 'INSTALL.txt')
    artifacts = [archive]
    if not portable_only:
        directory = installer_stage(root, stage, app)
        setup = output / names['setup']
        subprocess.run(
            [
                installer_creator(),
                '--offline-only',
                '-c',
                str(directory / 'config/config.xml'),
                '-p',
                str(directory / 'packages'),
                str(setup),
            ],
            check=True,
        )
        setup.chmod(setup.stat().st_mode | 0o111)
        artifacts.append(setup)
        if not skip_smoke:
            subprocess.run(
                [
                    sys.executable,
                    str(root / 'scripts/installer_smoke.py'),
                    '--installer',
                    str(setup),
                    '--work',
                    str(stage / 'installer-smoke'),
                ],
                check=True,
                timeout=480,
            )
            shutil.copy2(stage / 'installer-smoke/installer-report.json', output)
    return artifacts
