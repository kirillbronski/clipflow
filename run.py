"""Run ClipFlow from a checkout on Windows or macOS."""
from pathlib import Path
import runpy
import sys

source = Path(__file__).resolve().parent / 'source'
sys.path.insert(0, str(source))
runpy.run_path(str(source / 'clipflow.py'), run_name='__main__')
