# Third-party components

Dependencies retain their own licenses. Check the exact versions used for each distribution and include the applicable notices when publishing installers.

| Component | License / upstream |
|---|---|
| CustomTkinter | MIT; vendored license in `source/_internal/customtkinter-6.0.0.dist-info/licenses/LICENSE`; upstream https://github.com/TomSchimansky/CustomTkinter |
| yt-dlp | Unlicense, with separately licensed bundled code/dependencies; https://github.com/yt-dlp/yt-dlp |
| PySide6 / Qt | LGPLv3/GPLv3 or commercial options depending on modules; https://doc.qt.io/qtforpython-6/licenses.html |
| FFmpeg | LGPL/GPL depending on build configuration; https://ffmpeg.org/legal.html |
| Node.js | MIT plus bundled third-party notices; https://github.com/nodejs/node/blob/main/LICENSE |
| Python | PSF license; https://docs.python.org/3/license.html |
| PyInstaller | GPL with distribution exception; https://pyinstaller.org/en/stable/license.html |

FFmpeg/Node runtimes are not stored in this source repository. Packaging includes the binaries available on the build machine; their exact build configuration and corresponding redistribution obligations must be checked for each public binary release. This dependency list is not a replacement for their full license texts.

No license has yet been selected for ClipFlow's own code.
