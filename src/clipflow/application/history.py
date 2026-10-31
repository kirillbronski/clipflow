"""History file actions: recorded outputs; folders go once only system junk is left."""

from collections.abc import Iterable
from pathlib import Path

from clipflow.domain.models import TERMINAL_STATES, Job


class HistoryError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def result_status(job):
    """Completion records the attempt outcome; file presence is a separate fact."""
    if job.result_files and any(not path.is_file() for path in job.result_files):
        return 'files_missing'
    return job.state.value


def deletion_paths(jobs, all_jobs):
    """Validate the entire selection before unlinking even the first file."""
    paths = []
    for job in jobs:
        if job.state not in TERMINAL_STATES:
            raise HistoryError('job_busy')
        root = job.request.options.folder
        if root != root.resolve():
            raise HistoryError('unsafe_result_path')
        for value in job.result_files:
            path = Path(value)
            resolved = path.resolve()
            if (
                not path.is_absolute()
                or not path.is_relative_to(root)
                or not resolved.is_relative_to(root)
                or resolved == root
                or resolved != path
                or path.is_dir()
            ):
                raise HistoryError('unsafe_result_path')
            if any(
                other.state not in TERMINAL_STATES
                and (
                    resolved in (p.resolve() for p in other.result_files)
                    or resolved.is_relative_to(other.request.options.folder.resolve())
                )
                for other in all_jobs
            ):
                raise HistoryError('job_busy')
            paths.append(path)
    return tuple(dict.fromkeys(paths))


# Files the OS drops into folders a person has opened; they never hold anything of theirs.
_SYSTEM_JUNK = frozenset({'.DS_Store', 'Thumbs.db', 'desktop.ini'})


def prune_empty_folders(jobs):
    """After deleting results, remove folders they leave empty, up to but not including the root."""
    for job in jobs:
        root = job.request.options.folder
        for value in job.result_files:
            folder = Path(value).parent
            while folder != root and folder.is_relative_to(root):
                try:
                    entries = list(folder.iterdir())
                    if any(entry.name not in _SYSTEM_JUNK for entry in entries):
                        break
                    for entry in entries:
                        entry.unlink()
                    folder.rmdir()
                except OSError:
                    break
                folder = folder.parent


def removable_targets(jobs: Iterable[Job], pending: set[str]) -> set[str]:
    """Cleared jobs that may go: a kept child still needs its parent, and so on upwards."""
    jobs = tuple(jobs)
    targets = set(pending)
    while True:
        parents = {job.parent_id for job in jobs if job.id not in targets}
        smaller = targets - parents
        if smaller == targets:
            return targets
        targets = smaller
