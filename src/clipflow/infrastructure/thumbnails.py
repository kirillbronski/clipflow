"""Cover pictures of queue rows: one small JPEG per job beside the queue, gone with its job."""

import os
import re
from collections.abc import Iterable
from pathlib import Path
from tempfile import NamedTemporaryFile


def _identity(job_id):
    # The repository's rule for job ids, so a name can never leave the folder.
    if not isinstance(job_id, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', job_id):
        raise ValueError('invalid_job_identity')
    if job_id in {'.', '..'}:
        raise ValueError('invalid_job_identity')
    return job_id


class ThumbnailStore:
    def __init__(self, directory: Path):
        self.directory = Path(directory)

    def path(self, job_id: str) -> Path:
        return self.directory / f'{_identity(job_id)}.jpg'

    def exists(self, job_id: str) -> bool:
        return self.path(job_id).is_file()

    def save(self, job_id: str, data: bytes) -> None:
        target = self.path(job_id)
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with NamedTemporaryFile(dir=self.directory, suffix='.tmp', delete=False) as output:
                temporary = Path(output.name)
                output.write(data)
            os.replace(temporary, target)
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def remove(self, job_ids: Iterable[str]) -> None:
        for job_id in job_ids:
            self.path(job_id).unlink(missing_ok=True)

    def prune(self, keep_ids: set[str]) -> None:
        """Drop covers whose jobs are gone; other files in the folder are left alone."""
        try:
            entries = list(self.directory.iterdir())
        except OSError:
            return
        for entry in entries:
            if entry.suffix == '.jpg' and entry.stem not in keep_ids:
                entry.unlink(missing_ok=True)
