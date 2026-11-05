"""Keep the computer awake while downloads run; a failure here never stops a download."""

import contextlib
import os
import subprocess
import sys

_CONTINUOUS = 0x80000000
_SYSTEM_REQUIRED = 0x00000001


class KeepAwake:
    def __init__(self, run=subprocess.Popen, kernel32=None, system=None):
        self._run = run
        self._kernel32 = kernel32
        self._system = system or sys.platform
        self._process = None
        self._held = False

    def hold(self):
        if self._held:
            return
        self._held = True
        with contextlib.suppress(OSError, AttributeError, ValueError):
            if self._system == 'darwin':
                # -w: caffeinate ends with this program even if it is killed.
                self._process = self._run(
                    ['caffeinate', '-i', '-w', str(os.getpid())],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            elif self._system.startswith('linux'):
                self._process = self._run(
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
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            elif self._system == 'win32':
                self._windows().SetThreadExecutionState(_CONTINUOUS | _SYSTEM_REQUIRED)

    def release(self):
        if not self._held:
            return
        self._held = False
        with contextlib.suppress(OSError, AttributeError, ValueError, subprocess.SubprocessError):
            if self._process is not None:
                process, self._process = self._process, None
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:  # a stuck caffeinate must not keep the Mac up
                    process.kill()
                    process.wait(timeout=2)
            elif self._system == 'win32':
                self._windows().SetThreadExecutionState(_CONTINUOUS)

    def _windows(self):
        if self._kernel32 is None:
            import ctypes  # pragma: only windows

            self._kernel32 = ctypes.windll.kernel32  # pragma: only windows
        return self._kernel32
