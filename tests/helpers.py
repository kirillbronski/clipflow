"""Deterministic in-memory persistence, using the same repository contract, and waiting."""

import time


class MemoryJobRepository:
    def __init__(self):
        self.jobs = {}

    def add(self, job):
        if job.id in self.jobs:
            raise ValueError('Duplicate job ID')
        self.jobs[job.id] = job

    def get(self, job_id):
        return self.jobs[job_id]

    def list(self):
        return tuple(self.jobs.values())

    def update(self, job):
        if job.id not in self.jobs:
            raise KeyError(job.id)
        self.jobs[job.id] = job


def wait_until(predicate, timeout=10.0, interval=0.025):
    """Poll a condition outside the Qt event loop; fail with AssertionError on timeout."""
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError(f'condition not met within {timeout} s')
        time.sleep(interval)
