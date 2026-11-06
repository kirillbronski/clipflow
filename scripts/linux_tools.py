"""Fetch architecture-specific Linux tools with fixed upstream checksums."""

import argparse
import hashlib
import os
import shutil
import subprocess
import tarfile
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
PINS = {
    'x86_64': {
        'ffmpeg': {
            'url': 'https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-11-04-12-51/ffmpeg-n8.1.3-34-ga35157abb9-linux64-gpl-8.1.tar.xz',
            'sha256': '0fc51331600b02730e6d63485ac7e3cd203bdeeb13216cd78c8844aeb9277fb8',
        },
        'node': {
            'url': 'https://nodejs.org/dist/v22.23.4/node-v22.23.4-linux-x64.tar.xz',
            'sha256': '1805bcd35e6815559bd2eb97db438d3fdb0eb3a5e6a977b7c1badca76337e9ce',
        },
        'qtifw': {
            'url': 'https://download.qt.io/official_releases/qt-installer-framework/4.8.1/QtInstallerFramework-linux-x64-4.8.1.run',
            'sha256': '4b6f61a81b6560b27e40d5a25584685a8407642ac5430ba91e503f9b31986797',
        },
    },
    'aarch64': {
        'ffmpeg': {
            'url': 'https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-11-04-12-51/ffmpeg-n8.1.3-34-ga35157abb9-linuxarm64-gpl-8.1.tar.xz',
            'sha256': 'e4d93d4b858a341cf29cbcd0ce2e31271bba67018b27ff4ef3c2e1683f76b810',
        },
        'node': {
            'url': 'https://nodejs.org/dist/v22.23.4/node-v22.23.4-linux-arm64.tar.xz',
            'sha256': '6287aa46b6c375d816e63ae66d024fbbfd70404825aabdfdf898a970871d2f4b',
        },
    },
}


def _download(url, path):
    with urlopen(url, timeout=60) as response, path.open('wb') as stream:
        shutil.copyfileobj(response, stream)


def _sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def download_checked(url, destination, sha256, *, download=_download):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and _sha(destination) == sha256:
        return destination
    destination.unlink(missing_ok=True)
    try:
        download(url, destination)
        if _sha(destination) != sha256:
            raise RuntimeError('Download checksum mismatch: ' + destination.name)
    except (OSError, RuntimeError):
        destination.unlink(missing_ok=True)
        raise
    return destination


def _archive_tool(archive, destination, name, binaries, licenses):
    extracted = destination / ('extracted-' + name)
    extracted.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as stream:
        stream.extractall(extracted, filter='data')
    for binary in binaries:
        candidates = list(extracted.glob('*/bin/' + binary))
        if len(candidates) != 1:
            raise RuntimeError('Archive has no unique ' + binary)
        shutil.copy2(candidates[0], destination / 'bin' / binary)
    for filename in ('LICENSE', 'LICENSE.txt', 'COPYING.GPLv3', 'COPYING.LGPLv3'):
        for path in extracted.glob('*/' + filename):
            shutil.copy2(path, licenses / (name + '-' + filename + '.txt'))


def install_tools(arch, destination):
    destination = Path(destination).resolve()
    (destination / 'bin').mkdir(parents=True, exist_ok=True)
    licenses = ROOT / 'work/package-licenses'
    licenses.mkdir(parents=True, exist_ok=True)
    for name, binaries in [('ffmpeg', ('ffmpeg', 'ffprobe')), ('node', ('node',))]:
        pin = PINS[arch][name]
        archive = download_checked(pin['url'], destination / (name + '.tar.xz'), pin['sha256'])
        _archive_tool(archive, destination, name, binaries, licenses)
    return install_qtifw(arch, destination)


def install_qtifw(arch, destination):
    if arch == 'aarch64':
        from linux_qtifw import build_qtifw

        return build_qtifw(destination)
    pin = PINS[arch]['qtifw']
    setup = download_checked(pin['url'], destination / 'qtifw.run', pin['sha256'])
    setup.chmod(setup.stat().st_mode | 0o111)
    creator = destination / 'qtifw/bin/binarycreator'
    if not creator.is_file():
        subprocess.run(
            [
                str(setup),
                '--root',
                str(destination / 'qtifw'),
                '--accept-licenses',
                '--default-answer',
                '--confirm-command',
                'install',
            ],
            env=dict(os.environ, QT_QPA_PLATFORM='minimal'),
            check=True,
            timeout=300,
        )
    if not creator.is_file():
        raise RuntimeError('QtIFW installation has no binarycreator')
    return creator


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arch', choices=tuple(PINS), required=True)
    parser.add_argument('--dest', type=Path, required=True)
    args = parser.parse_args()
    print(install_tools(args.arch, args.dest))


if __name__ == '__main__':
    main()
