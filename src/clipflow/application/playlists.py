"""Playlist files for players: an ordered .m3u8 beside a playlist's tracks."""

import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

from clipflow.domain.paths import safe_name


@dataclass(frozen=True)
class M3uEntry:
    path: Path
    title: str
    duration: float | None
    index: int  # the track's position in the playlist


def m3u_text(entries: Sequence[M3uEntry], base: Path) -> str:
    """#EXTM3U with one #EXTINF line per track, paths relative to the list, forward slashes."""
    lines = ['#EXTM3U']
    for entry in sorted(entries, key=lambda e: e.index):
        seconds = round(entry.duration) if entry.duration else -1
        relative = Path(os.path.relpath(entry.path, base)).as_posix()
        lines += [f'#EXTINF:{seconds},{entry.title}', relative]
    return '\n'.join(lines) + '\n'


def m3u_location(title: str, files: Sequence[Path], root: Path) -> Path | None:
    """The shared folder of the files inside the download folder, else nowhere."""
    if not files:
        return None
    try:
        common = Path(os.path.commonpath([str(path.parent) for path in files]))
    except ValueError:  # different drives
        return None
    if not common.is_relative_to(root):
        return None
    return common / f'{safe_name(title, 80)}.m3u8'


def write_m3u(path: Path, text: str) -> None:
    """Atomically: a player never reads a half-written list."""
    temporary = None
    try:
        with NamedTemporaryFile(
            'w', encoding='utf-8', dir=path.parent, suffix='.tmp', delete=False
        ) as output:
            temporary = Path(output.name)
            output.write(text)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
