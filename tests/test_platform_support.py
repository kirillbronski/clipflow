"""Verify native paths, preserved Windows settings and platform dispatch."""
from pathlib import Path
from unittest.mock import patch
import os
import runpy
import sys
import tempfile
sys.path.insert(0, 'source')
import platform_support as support

with tempfile.TemporaryDirectory() as temp:
    with patch.dict(os.environ, {'LOCALAPPDATA':temp}, clear=True), patch.object(sys,'platform','win32'):
        windows=runpy.run_path('source/platform_support.py')
        assert windows['APP_DATA']==Path(temp)/'ClipFlow'
        assert windows['SETTINGS_DIR']==Path(temp)/'YouTubeDownloader'
        assert windows['AUTH_DIR']==Path(temp)/'ClipFlow/YouTubeAuth'
        assert windows['MODIFIER']=='Control'
        assert windows['platform_text']('⌘+N · macOS Keychain')=='Ctrl+N · Windows DPAPI'
    with patch.dict(os.environ, {'CLIPFLOW_DATA_DIR':temp}, clear=True):
        isolated=runpy.run_path('source/platform_support.py')
        assert isolated['SETTINGS_DIR']==Path(temp).resolve()
        assert isolated['APP_DATA']==Path(temp).resolve()
    fake=Path(temp)/('ffmpeg.exe' if support.IS_WINDOWS else 'ffmpeg')
    fake.write_bytes(b'test fixture')
    with patch.dict(os.environ, {'CLIPFLOW_BIN_DIR':temp}):
        assert support.binary_path('ffmpeg')==str(fake)
if support.IS_WINDOWS:
    plain=b'ClipFlow DPAPI regression fixture'
    encrypted=support.protect_profile(plain)
    assert encrypted!=plain
    assert support.protect_profile(encrypted,decrypt=True)==plain
print('PASS native paths, legacy Windows settings, platform labels, binary lookup and native encryption dispatch')
