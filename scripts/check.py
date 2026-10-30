"""Run the supported Qt suite and all runtime coverage gates."""

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--qt', action='store_true', help='Compatibility alias; Qt is the only runtime'
    )
    parser.parse_args(argv)
    from check_coverage import run

    result = run()
    if not result:
        print('All offline Qt checks and coverage gates passed.', flush=True)
    return result


if __name__ == '__main__':
    raise SystemExit(main())
