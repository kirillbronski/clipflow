"""Playlists and profiles shown as one row: which jobs belong together and their summary."""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from clipflow.domain.models import TERMINAL_STATES, ContentKind, Job, JobState

_GROUP_KINDS = frozenset({ContentKind.PLAYLIST, ContentKind.PROFILE})
_WORKING = (JobState.DOWNLOADING, JobState.PROCESSING, JobState.PROBING)


def is_group(job: Job, has_descendants: bool) -> bool:
    """A top-level job that collects others: a playlist or profile, or anything with children."""
    return job.parent_id is None and (job.request.link.kind in _GROUP_KINDS or has_descendants)


def top_level_id(job_id: str, jobs_by_id: Mapping[str, Job]) -> str | None:
    """The root of a job's parent chain, or None when the chain leads to a removed job."""
    seen = set()
    while job_id in jobs_by_id and job_id not in seen:
        seen.add(job_id)
        parent = jobs_by_id[job_id].parent_id
        if parent is None:
            return job_id
        job_id = parent
    return None


def descendants(jobs: Iterable[Job]) -> dict[str, tuple[Job, ...]]:
    """Every top-level job with all jobs linked to it through parent_id, in list order."""
    jobs = tuple(jobs)
    by_id = {job.id: job for job in jobs}
    roots: dict[str, str | None] = {}

    def root(job_id):
        # Each job is walked once: the chain's answer is remembered for all its links.
        chain = []
        while True:
            if job_id in roots:
                result = roots[job_id]
                break
            job = by_id.get(job_id)
            if job is None or job_id in chain:
                result = None
                break
            if job.parent_id is None:
                result = job_id
                break
            chain.append(job_id)
            job_id = job.parent_id
        for item in chain:
            roots[item] = result
        return result

    groups: dict[str, list[Job]] = {job.id: [] for job in jobs if job.parent_id is None}
    for job in jobs:
        if job.parent_id is not None:
            top = root(job.id)
            if top is not None:
                groups[top].append(job)
    return {key: tuple(value) for key, value in groups.items()}


@dataclass(frozen=True)
class GroupSummary:
    total: int
    completed: int
    failed: int
    active: int
    size_bytes: int
    current: Job | None
    parent: Job


def group_summary(parent: Job, members: Sequence[Job], sizes: Mapping[str, int]) -> GroupSummary:
    """Counts for the group row (cancelled is not a failure); sizes come from the caller."""
    completed = [job for job in members if job.state == JobState.COMPLETED]
    return GroupSummary(
        total=len(members),
        completed=len(completed),
        failed=sum(job.state == JobState.FAILED for job in members),
        active=sum(job.state not in TERMINAL_STATES for job in members),
        size_bytes=sum(sizes.get(job.id, 0) for job in completed),
        current=next((job for job in members if job.state in _WORKING), None),
        parent=parent,
    )
