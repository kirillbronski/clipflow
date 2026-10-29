"""Compatibility for the source-only legacy entry until retirement in T16."""
from pathlib import Path
import runpy
APP_VERSION=runpy.run_path(str(Path(__file__).resolve().parents[1]/'src/clipflow/version.py'))['APP_VERSION']
