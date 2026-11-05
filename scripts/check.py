"""Run the style gate, the supported Qt suite and all runtime coverage gates."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINT_COMMANDS = (
    ('ruff', 'format', '--check', '.'),
    ('ruff', 'check', '.'),
)


def lint(run=subprocess.run):
    """Fail fast on formatting or lint findings; ruff output stays visible in CI logs."""
    for command in LINT_COMMANDS:
        result = run([sys.executable, '-m', *command], cwd=ROOT)
        if result.returncode:
            return result.returncode
    return 0


def main(argv=None, *, run=subprocess.run):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--qt', action='store_true', help='Compatibility alias; Qt is the only runtime'
    )
    parser.parse_args(argv)
    # pytest writes .coverage under the repository root; read it from there too.
    os.chdir(ROOT)
    result = lint(run)
    if result:
        return result
    # Like the CI offline job: no real screen, focus or display scale can fail the suite.
    # Native GUI checks run separately with an explicit QT_QPA_PLATFORM (docs/TESTING.md).
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from check_coverage import run

    result = run()
    if not result:
        print('All offline Qt checks and coverage gates passed.', flush=True)
    return result


if __name__ == '__main__':
    raise SystemExit(main())
