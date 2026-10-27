"""Deterministic in-memory persistence, using the same repository contract."""


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
