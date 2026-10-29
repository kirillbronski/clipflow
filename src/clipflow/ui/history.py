"""History file actions: recorded outputs only, never recursive folder deletion."""
from pathlib import Path

from clipflow.domain.models import TERMINAL_STATES


class HistoryError(Exception):
    def __init__(self,code): self.code=code; super().__init__(code)


def result_status(job):
    """Completion records the attempt outcome; file presence is a separate fact."""
    if job.result_files and any(not path.is_file() for path in job.result_files):
        return 'files_missing'
    return job.state.value


def deletion_paths(jobs, all_jobs):
    """Validate the entire selection before unlinking even the first file."""
    paths=[]
    for job in jobs:
        if job.state not in TERMINAL_STATES: raise HistoryError('job_busy')
        root=job.request.options.folder
        if root!=root.resolve(): raise HistoryError('unsafe_result_path')
        for value in job.result_files:
            path=Path(value)
            resolved=path.resolve()
            if (not path.is_absolute() or not path.is_relative_to(root)
                    or not resolved.is_relative_to(root) or resolved==root
                    or resolved!=path or path.is_dir()):
                raise HistoryError('unsafe_result_path')
            if any(other.state not in TERMINAL_STATES and
                   (resolved in (p.resolve() for p in other.result_files)
                    or resolved.is_relative_to(other.request.options.folder.resolve()))
                   for other in all_jobs):
                raise HistoryError('job_busy')
            paths.append(path)
    return tuple(dict.fromkeys(paths))
