"""Run offline regression checks with isolated profiles and no account login."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='clipflow-check-') as temp:
    commands = [[sys.executable, ROOT/'run.py', '--ui-self-test']]
    commands += [[sys.executable, path] for path in sorted((ROOT/'tests').glob('test_*.py'))]
    for index, command in enumerate(commands):
        env = dict(os.environ, CLIPFLOW_DATA_DIR=str(Path(temp)/str(index)))
        print('CHECK', Path(command[1]).name, flush=True)
        subprocess.run([str(arg) for arg in command], cwd=ROOT, env=env, check=True, timeout=90)
print('All offline checks passed.', flush=True)
