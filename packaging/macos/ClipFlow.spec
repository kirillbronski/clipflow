from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules
import runpy

root = Path(SPECPATH).resolve().parents[1]
src = root / 'source'
version = runpy.run_path(str(src / 'version.py'))['APP_VERSION']
data = [(str(src / name), '.') for name in ('clipflow.png', 'clipflow-getcourse.png', 'clipflow-instagram.png')]
data += [(str(src / '_internal/customtkinter/assets'), 'customtkinter/assets')]
data += collect_data_files('yt_dlp_ejs')
hidden = collect_submodules('yt_dlp') + collect_submodules('yt_dlp_ejs')
hidden += ['keyring.backends.macOS', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets']
tools = [(str(Path('/opt/homebrew/bin') / name), 'bin') for name in ('ffmpeg', 'ffprobe', 'node')]
a = Analysis([str(src / 'clipflow.py')], pathex=[str(src), str(src / '_internal')],
             binaries=tools, datas=data, hiddenimports=hidden,
             excludes=['PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.Qt3DCore', 'PySide6.QtCharts'],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='ClipFlow',
          debug=False, strip=False, upx=False, console=False, target_arch='arm64')
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='ClipFlow')
app = BUNDLE(coll, name='ClipFlow.app', icon=str(root / 'assets/icons/clipflow.icns'),
             bundle_identifier='com.clipflow.desktop',
             info_plist={'CFBundleShortVersionString': version, 'CFBundleVersion': version,
                         'NSHighResolutionCapable': True,
                         'NSHumanReadableCopyright': 'ClipFlow; bundled components retain their respective licenses.',
                         'LSMinimumSystemVersion': '27.0'})
