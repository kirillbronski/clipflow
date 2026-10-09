#!/bin/zsh
set -euo pipefail
cd "${0:A:h}"
clipflow_version="$(.venv/bin/python -c 'import sys; sys.path.insert(0, "source"); from version import APP_VERSION; print(APP_VERSION)')"
.venv/bin/python -m PyInstaller --noconfirm --clean --distpath outputs --workpath work/build ClipFlow.spec
codesign --verify --deep --strict outputs/ClipFlow.app
rm -rf work/dmg
mkdir -p work/dmg
ditto outputs/ClipFlow.app work/dmg/ClipFlow.app
ln -sfn /Applications work/dmg/Applications
cp INSTALL.txt work/dmg/
hdiutil create -volname "ClipFlow ${clipflow_version}" -srcfolder work/dmg -ov -format UDZO "outputs/ClipFlow-${clipflow_version}-macOS-arm64.dmg"
hdiutil verify "outputs/ClipFlow-${clipflow_version}-macOS-arm64.dmg"
