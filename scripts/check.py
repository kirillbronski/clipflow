"""Offline checks; --qt runs the new application suite and coverage gates."""
from pathlib import Path
import argparse
import os
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--qt',action='store_true')
    args=parser.parse_args(argv)
    if not args.qt:
        with tempfile.TemporaryDirectory(prefix='clipflow-legacy-check-') as temp:
            commands=[[sys.executable,ROOT/'run.py','--ui-self-test']]
            commands += [[sys.executable,p] for p in sorted((ROOT/'tests').glob('test_*.py'))]
            for index,command in enumerate(commands):
                print('CHECK',Path(command[1]).name,flush=True)
                subprocess.run([str(arg) for arg in command],cwd=ROOT,
                    env=dict(os.environ,CLIPFLOW_DATA_DIR=str(Path(temp)/str(index))),check=True,timeout=90)
    from check_coverage import run
    result=run()
    if not result: print('All offline Qt checks and coverage gates passed.',flush=True)
    return result

if __name__=='__main__': raise SystemExit(main())
