# Third-party components

Dependencies retain their own licenses. Check the exact versions used for each distribution and include the applicable notices when publishing installers.

| Component | License / upstream |
|---|---|
| CustomTkinter | MIT; historical license retained at `assets/licenses/CustomTkinter-LICENSE.txt`; retired from the 2.0 runtime; upstream https://github.com/TomSchimansky/CustomTkinter |
| yt-dlp | Unlicense, with separately licensed bundled code/dependencies; https://github.com/yt-dlp/yt-dlp |
| PySide6 / Qt | LGPLv3/GPLv3 or commercial options depending on modules; https://doc.qt.io/qtforpython-6/licenses.html |
| FFmpeg | LGPL/GPL depending on build configuration; https://ffmpeg.org/legal.html |
| Node.js | MIT plus bundled third-party notices; https://github.com/nodejs/node/blob/main/LICENSE |
| Python | PSF license; https://docs.python.org/3/license.html |
| PyInstaller | GPL with distribution exception; https://pyinstaller.org/en/stable/license.html |

FFmpeg/Node runtimes are not stored in this source repository. Packaging includes the binaries available on the build machine; their exact build configuration and corresponding redistribution obligations must be checked for each public binary release. This dependency list is not a replacement for their full license texts.

ClipFlow's own code is published without an open-source license. See COPYRIGHT.md. This does not change the licenses of third-party components.


## Pinned Linux distribution tools

- FFmpeg GPL build: BtbN `autobuild-2026-11-04-12-51`,
  `n8.1.3-34-ga35157abb9`, linux64/linuxarm64 GPL 8.1 archives.
  Upstream builds/source configuration: https://github.com/BtbN/FFmpeg-Builds/tree/autobuild-2026-11-04-12-51 .
  Archive LICENSE.txt and existing GPL texts accompany distributions.
- Node.js v22.23.4, linux-x64/linux-arm64; vendor LICENSE copied from the archive.
  Source/license: https://github.com/nodejs/node/tree/v22.23.4 .
- Qt Installer Framework 4.8.1: official Linux x64 tools; ARM64 tools use QtIFW 4.11.0 built from
  vendor sources against static Qt 6.7.2 (qtbase, qtdeclarative, qttools, qt5compat).
  Source archive SHA256 values and build commands are in scripts/linux_qtifw.py. Build tools
  are not included in the ClipFlow application; the generated installer uses QtIFW.
  GPLv3 with the Qt Installer Framework distribution exception and third-party
  notices are retained under assets/licenses/QtIFW-*.
  Source: https://download.qt.io/official_releases/qt-installer-framework/4.8.1/ .
- SecretStorage and Jeepney: Linux Secret Service backend dependencies of keyring;
  their installed package metadata/notices are collected by PyInstaller.

Exact download URLs and architecture-specific SHA256 values: scripts/linux_tools.py.
The licensing policy for ClipFlow's own code is unchanged.
