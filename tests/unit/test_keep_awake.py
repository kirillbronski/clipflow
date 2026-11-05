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
    guard = KeepAwake(run=None, system='sunos5')
    guard.hold()
    guard.release()


def test_release_survives_a_stuck_caffeinate():
    import subprocess

    class Stuck(Process):
        killed = False

        def wait(self, timeout=None):
            if not self.killed:
                raise subprocess.TimeoutExpired('caffeinate', timeout)
            return 0

        def kill(self):
            self.killed = True

    started = []
    guard = KeepAwake(
        run=lambda args, **kwargs: started.append(Stuck(args)) or started[-1], system='darwin'
    )
    guard.hold()
    guard.release()  # must not raise on the 500 ms tick
    assert started[0].killed
    guard.hold()
    assert len(started) == 2  # released state is clean: the next hold starts anew


def test_linux_hold_runs_systemd_inhibit_bound_to_pid():
    started = []

    def run(args, **kwargs):
        started.append(Process(args))
        return started[-1]

    guard = KeepAwake(run=run, system='linux')
    guard.hold()
    guard.hold()
    assert [p.args for p in started] == [
        [
            'systemd-inhibit',
            '--what=sleep:idle',
            '--who=ClipFlow',
            '--why=Downloads in progress',
            '--mode=block',
            'tail',
            f'--pid={os.getpid()}',
            '-f',
            '/dev/null',
        ]
    ]
    guard.release()
    assert started[0].terminated


def test_linux_missing_systemd_inhibit_is_silent():
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        raise FileNotFoundError('systemd-inhibit')

    guard = KeepAwake(run=run, system='linux')
    guard.hold()
    guard.release()
    guard.hold()
    guard.release()
    assert len(calls) == 2
