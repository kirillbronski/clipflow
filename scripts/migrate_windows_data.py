"""Import previous app data into ClipFlow without replacing existing files."""

from pathlib import Path
import argparse
import json
import shutil
import sys

FILES = ('settings.json', 'getcourse-profile.dat')


def migrate(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_dir() or source == destination:
        raise ValueError('Select a separate existing directory with previous app data.')
    candidates = [source / name for name in FILES if (source / name).is_file()]
    if not candidates or any(path.is_symlink() for path in candidates):
        raise ValueError('No supported regular app data files found.')
    settings = source / 'settings.json'
    if settings in candidates:
        if not isinstance(json.loads(settings.read_text(encoding='utf-8')), dict):
            raise ValueError('Settings must contain a JSON object.')
    destination.mkdir(parents=True, exist_ok=True)
    result = {}
    for path in candidates:
        target = destination / path.name
        try:
            output = target.open('xb')
        except FileExistsError:
            result[path.name] = 'kept existing ClipFlow file'
            continue
        try:
            with output, path.open('rb') as original:
                shutil.copyfileobj(original, output)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        result[path.name] = 'copied; original preserved'
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    args = parser.parse_args(argv)
    if sys.platform != 'win32':
        parser.error('Run this import on the Windows computer under the original user account.')
    from clipflow.infrastructure.platform import data_directory

    try:
        for name, status in migrate(args.source, data_directory()).items():
            print(f'{name}: {status}')
    except (OSError, ValueError):
        raise SystemExit(
            'Import failed. Check the selected directory, file format and permissions. Originals were preserved.'
        )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
