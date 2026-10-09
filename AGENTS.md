# ClipFlow unified project

This repository is the authoritative shared source for Windows and macOS. Edit `source/clipflow.py` and common modules once; keep platform behavior in `source/platform_support.py` and packaging files in `packaging/`.

- Start each session with `git status`, inspect the branch/upstream and read these instructions. Never overwrite unrelated user changes.
- On a clean checkout, fetch/pull before new work; use a focused feature/fix branch for changes after initial migration.
- Validate with the checkout's Python 3.12 environment: `python scripts/check.py`. Build with `python scripts/build.py` on the target OS.
- Preserve historical storage: Windows settings/GetCourse in LocalAppData/YouTubeDownloader, Windows sessions in LocalAppData/ClipFlow; macOS data in Library/Application Support/ClipFlow.
- Keep user credentials, cookie stores, keys and machine paths out of Git. Use `CLIPFLOW_DATA_DIR` for all tests.
- Commit coherent verified changes with a clear message; push authorized completed work to the corresponding remote branch. Report commit and check results. Never force-push shared history.
- GUI/network mock tests do not replace packaged checks. Verify embedded auth and installer integrity before a release. Clearly report which OS was actually tested.
- Keep one installed macOS app. After verified packaging/install, unregister and remove temporary app copies, preserving the DMG/ZIP.
- The legacy Google Drive `Windows` project is a read-only baseline during migration. Do not edit, rename or delete it. Drive holds release archives/backups; do not sync `.git` or `.venv` through Drive.
- The installed 1.8.4 apps predate this refactor. Do not present them as builds of the unified source until rebuilt and tested.
