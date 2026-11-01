"""Keeping the computer awake while downloading: caffeinate on macOS, Windows API there."""

import os

from clipflow.infrastructure.keep_awake import KeepAwake


class Process:
    def __init__(self, args):
        self.args = args
        self.terminated = False

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0


def test_hold_and_release_on_mac():
    started = []

    def run(args, **kwargs):
        started.append(Process(args))
        return started[-1]

    guard = KeepAwake(run=run, system='darwin')
    guard.hold()
    guard.hold()  # holding twice starts one process
    assert [p.args for p in started] == [['caffeinate', '-i', '-w', str(os.getpid())]]
    guard.release()
    assert started[0].terminated
    guard.release()  # releasing twice is harmless


class Kernel:
    def __init__(self):
        self.calls = []

    def SetThreadExecutionState(self, flags):  # the Windows API name
        self.calls.append(flags)
        return 1


def test_hold_and_release_on_windows():
    kernel = Kernel()
    guard = KeepAwake(kernel32=kernel, system='win32')
    guard.hold()
    guard.hold()
    guard.release()
    assert kernel.calls == [0x80000001, 0x80000000]


def test_launch_failure_is_silent():
    def run(args, **kwargs):
        raise OSError('no caffeinate')

    guard = KeepAwake(run=run, system='darwin')
    guard.hold()
    guard.release()


def test_other_systems_do_nothing():
    guard = KeepAwake(run=None, system='linux')
    guard.hold()
    guard.release()
