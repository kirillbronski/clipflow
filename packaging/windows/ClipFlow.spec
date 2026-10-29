from pathlib import Path
import sys
root=Path(SPECPATH).resolve().parents[1]
sys.path.insert(0,str(root/'scripts'))
from package_config import APP_VERSION,spec_inputs
a=Analysis([str(root/'src/clipflow/__main__.py')],**spec_inputs(root,'windows'))
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='ClipFlow',
        icon=str(root/'assets/icons/clipflow.ico'),version=str(root/'work/windows-version.txt'),
        debug=False,strip=False,upx=False,console=False)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='ClipFlow')
