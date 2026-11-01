"""A controllable executor and YouTube requests for queue tests."""

from pathlib import Path

from clipflow.domain.events import (
    JobEvent,
)
from clipflow.domain.models import DownloadOptions, DownloadRequest, Service
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


_ADDRESSES = {
    Service.YOUTUBE: 'https://youtu.be/{}',
    Service.INSTAGRAM: 'https://www.instagram.com/p/{}/',
    Service.GETCOURSE: 'https://school.getcourse.ru/pl/teach/control/lesson/view?id={}',
}


def request(name='first', service=Service.YOUTUBE):
    """A GetCourse lesson needs a numeric name."""
    return DownloadRequest(
        parse_url(_ADDRESSES[service].format(name)), DownloadOptions(Path('/downloads'))
    )
