"""Native sign-in helpers: a fake auth child process and a saved session seed."""

import json

from clipflow.domain.models import Service


class Process:
    def __init__(self, *args, **kwargs):
        self.returncode = None
        self.terminated = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    def kill(self):
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


def seed(directory, service, protect):
    folder = directory / ('YouTubeAuth' if service == Service.YOUTUBE else 'InstagramAuth')
    folder.mkdir(parents=True, exist_ok=True)
    cookie = dict(
        domain='.youtube.com' if service == Service.YOUTUBE else '.instagram.com',
        path='/',
        name='SAPISID' if service == Service.YOUTUBE else 'sessionid',
        value='synthetic-private-token',
        expires=-1,
        secure=True,
        httpOnly=True,
    )
    (folder / 'session.dat').write_bytes(protect(json.dumps([cookie]).encode()))
    return folder
