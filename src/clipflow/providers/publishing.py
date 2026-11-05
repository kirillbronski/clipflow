"""Publishing finished files: never overwrite another material, captions written atomically."""

import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from clipflow.providers.base import MediaFailure


def numbered(target, n):
    return target if n == 1 else target.with_name(f'{target.stem} ({n}){target.suffix}')


def find_tagged(target, tag, context, probe):
    """The finished file of this identity, if a numbered variant of the name holds it."""
    for n in range(1, 100):
        candidate = numbered(target, n)
        if candidate.is_file():
            try:
                tags = probe(candidate, context).get('format', {}).get('tags') or {}
            except MediaFailure:
                continue  # unreadable foreign file: not ours, keep looking
            if any(key.lower() == 'comment' and value == tag for key, value in tags.items()):
                return candidate
    return None


def publish(temporary, target):
    # Never replace an equally named file of another video: link fails if the name is taken.
    for n in range(1, 100):
        candidate = numbered(target, n)
        try:
            os.link(temporary, candidate)
        except FileExistsError:
            continue
        except OSError:
            if candidate.exists():
                continue
            os.replace(temporary, candidate)  # volume without hard links
            return candidate
        temporary.unlink()
        return candidate
    raise MediaFailure('write_failed')


def write_caption(target, description, fmt):
    caption = target.with_suffix('.' + fmt)
    temporary = None
    try:
        with NamedTemporaryFile(
            mode='w',
            encoding='utf-8-sig' if fmt == 'txt' else 'utf-8',
            newline='',
            dir=caption.parent,
            prefix=caption.name + '.',
            suffix='.tmp',
            delete=False,
        ) as output:
            temporary = Path(output.name)
            output.write(description)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, caption)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return caption
