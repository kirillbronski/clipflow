"""External tools run with cancellation; a stopped job never leaves a tool running."""

import contextlib
import os
import signal
import subprocess
from pathlib import Path

from clipflow.providers.base import MediaFailure


def run_process(args, context, *, capture=False, capture_error=False, expected_retcodes=(0,)):
    context.cancel.raise_if_cancelled()
    try:
        with subprocess.Popen(
            args,
            stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
            stderr=subprocess.PIPE if capture_error else subprocess.DEVNULL,
            start_new_session=os.name != 'nt',
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
        ) as process:
            try:
                while True:
                    try:
                        output, errors = process.communicate(timeout=0.1)
                        break
                    except subprocess.TimeoutExpired:
                        context.cancel.raise_if_cancelled()
                context.cancel.raise_if_cancelled()
                if process.returncode not in expected_retcodes:
                    raise MediaFailure('processing_failed')
                return errors if capture_error else output
            except BaseException:
                if process.poll() is None:
                    stop_process_tree(process)
                    try:
                        process.communicate(timeout=2)
                    except subprocess.TimeoutExpired:
                        stop_process_tree(process, force=True)
                        process.communicate(timeout=2)
                raise
    except FileNotFoundError:
        raise MediaFailure('tool_missing') from None


def stop_process_tree(process, force=False):
    if os.name == 'nt':
        # Chocolatey and user launchers can own the actual FFmpeg child.
        # Kill the tree while its root still exists, then drain inherited
        # pipes: killing just the shim can leave communicate() blocked.
        taskkill = Path(os.environ.get('SYSTEMROOT', 'C:/Windows')) / 'System32/taskkill.exe'
        with contextlib.suppress(OSError, subprocess.TimeoutExpired):
            subprocess.run(
                [str(taskkill), '/PID', str(process.pid), '/T', '/F'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        if process.poll() is None:
            process.kill()
    else:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL if force else signal.SIGTERM)
