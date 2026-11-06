"""Build the ARM64 QtIFW against static Qt, without obsolete image-format libraries."""

import json
import os
import shutil
import subprocess
import tarfile
from pathlib import Path

QT_VERSION = '6.7.2'
IFW_VERSION = '4.11.0'
SOURCE_SHA256 = {
    'qtbase': 'c5f22a5e10fb162895ded7de0963328e7307611c688487b5d152c9ee64767599',
    'qtdeclarative': '4c29cba1af8c42d425d8eb6e01bad24cb80f4b983d71eef566a0542dfdb9b999',
    'qttools': '58e855ad1b2533094726c8a425766b63a04a0eede2ed85086860e54593aa4b2a',
    'qt5compat': '8826b5189efc4d9bdb64fdb1aa89d0fdf4e53c60948ed7995621ed046e38c003',
    'qtifw': '4abdad903a52b1c20bb46c715d7d12c65905791a3e366e574212fdd74cc47629',
}


def _run(args, cwd):
    subprocess.run(list(map(str, args)), cwd=cwd, check=True)


def _source(module, directory):
    from linux_tools import download_checked

    if module == 'qtifw':
        filename = f'installer-framework-everywhere-src-{IFW_VERSION}'
        base = f'https://download.qt.io/official_releases/qt-installer-framework/{IFW_VERSION}'
    else:
        filename = f'{module}-everywhere-src-{QT_VERSION}'
        base = f'https://download.qt.io/archive/qt/6.7/{QT_VERSION}/submodules'
    archive = download_checked(
        f'{base}/{filename}.tar.xz', directory / (filename + '.tar.xz'), SOURCE_SHA256[module]
    )
    with tarfile.open(archive) as stream:
        roots = {Path(item.name).parts[0] for item in stream.getmembers() if item.name}
        if len(roots) != 1:
            raise RuntimeError('Source archive must contain one root directory')
        stream.extractall(directory, filter='data')
    return directory / roots.pop()


def _qt(module, source, build, prefix):
    build.mkdir()
    if module == 'qtbase':
        args = [
            source / 'configure',
            '-prefix',
            prefix,
            '-release',
            '-static',
            '-accessibility',
            '-qt-zlib',
            '-qt-libpng',
            '-qt-libjpeg',
            '-qt-pcre',
            '-no-glib',
            '-no-cups',
            '-no-sql-sqlite',
            '-no-feature-gssapi',
            '-no-opengl',
            '-no-egl',
            '-no-sm',
            '-no-icu',
            '-nomake',
            'examples',
            '-nomake',
            'tests',
            '-no-libudev',
            '-bundled-xcb-xinput',
            '-qt-harfbuzz',
            '-qt-doubleconversion',
            '-opensource',
            '-confirm-license',
        ]
    else:
        args = [prefix / 'bin/qt-configure-module', source]
        if module == 'qtdeclarative':
            args += ['-no-qml-debug']
        if module == 'qttools':
            args += ['--', '-DCMAKE_DISABLE_FIND_PACKAGE_Clang=ON']
    _run(args, build)
    _run(['cmake', '--build', '.', '--parallel', str(min(4, os.cpu_count() or 1))], build)
    _run(['cmake', '--install', '.'], build)


def _probe(directory):
    env = dict(os.environ, QT_QPA_PLATFORM='minimal')
    for name in ('binarycreator', 'installerbase'):
        subprocess.run([str(directory / 'bin' / name), '--help'], env=env, check=True, timeout=30)


def build_qtifw(destination):
    destination = Path(destination).resolve()
    target = destination / 'qtifw'
    marker = target / 'source-build.json'
    if marker.is_file() and json.loads(marker.read_text()) == SOURCE_SHA256:
        _probe(target)
        return target / 'bin/binarycreator'
    build = destination / 'qtifw-source-build'
    shutil.rmtree(build, ignore_errors=True)
    build.mkdir(parents=True)
    prefix = build / 'qt-static'
    for module in ('qtbase', 'qtdeclarative', 'qttools', 'qt5compat'):
        source = _source(module, build)
        _qt(module, source, build / (module + '-build'), prefix)
    source = _source('qtifw', build)
    _run([prefix / 'bin/qmake', 'CONFIG+=release', 'CONFIG+=lzmasdk'], source)
    _run(['make', '-j' + str(min(4, os.cpu_count() or 1))], source)
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(source / 'bin', target / 'bin')
    _probe(target)
    marker.write_text(json.dumps(SOURCE_SHA256, sort_keys=True) + '\n')
    return target / 'bin/binarycreator'
