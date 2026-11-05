import sys
from pathlib import Path

root = Path(SPECPATH).resolve().parents[1]
sys.path.insert(0, str(root / 'scripts'))
from package_config import APP_VERSION, spec_inputs

a = Analysis([str(root / 'src/clipflow/__main__.py')], **spec_inputs(root, 'macos'))
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ClipFlow',
    debug=False,
    strip=False,
    upx=False,
    console=False,
    target_arch='arm64',
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='ClipFlow')
app = BUNDLE(
    coll,
    name='ClipFlow.app',
    icon=str(root / 'assets/icons/clipflow.icns'),
    bundle_identifier='com.clipflow.desktop',
    info_plist={
        'CFBundleShortVersionString': APP_VERSION,
        'CFBundleVersion': APP_VERSION,
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '27.0',
        'NSHumanReadableCopyright': (
            'ClipFlow; bundled components retain their respective licenses.'
        ),
    },
)
