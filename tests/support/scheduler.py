"""A controllable executor and YouTube requests for queue tests."""

from pathlib import Path

from clipflow.domain.events import (
    JobEvent,
)
from clipflow.domain.models import DownloadOptions, DownloadRequest
from clipflow.domain.urls import parse_url


class ControlledExecutor:
    """External worker boundary; termination can deliberately arrive late."""

    def __init__(self):
        self.runs = []
        self.stops = []

    def start(self, job, on_event):
        self.runs.append((job, on_event))

    def stop(self, job_id, reason):
        self.stops.append((job_id, reason))

    def emit(self, payload, run=-1):
        job, callback = self.runs[run]
        callback(JobEvent(job.id, job.attempt_id, payload))


def request(name='first'):
    return DownloadRequest(
        parse_url(f'https://youtu.be/{name}'), DownloadOptions(Path('/downloads'))
    )
