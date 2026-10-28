"""Run ClipFlow from a checkout on Windows or macOS."""
from pathlib import Path
import runpy
import sys

if '--qt-preview' in sys.argv:
    # Import the installed src package before adding the legacy source path;
    # source/clipflow.py must never shadow the new clipflow package.
    from clipflow.ui.bootstrap import main
    raise SystemExit(main([arg for arg in sys.argv if arg!='--qt-preview']))
else:
    source = Path(__file__).resolve().parent / 'source'
    sys.path.insert(0, str(source))
    runpy.run_path(str(source / 'clipflow.py'), run_name='__main__')
