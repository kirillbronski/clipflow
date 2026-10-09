# Migration from separate 1.8.4 projects

The unified tree starts from verified macOS 1.8.4, which had already incorporated the Windows 1.8.4 application features. The original Windows tree remains unchanged as a baseline; source archives were saved before migration.

- Renamed the main module from downloader.py to clipflow.py.
- Isolated DPAPI/Keychain, native shortcuts/fonts, paths and binary discovery.
- Preserved legacy Windows settings/GetCourse and session directories.
- Retained macOS redraw batching, throttled telemetry, stale-run protection and the CustomTkinter tab callback fix.
- Replaced machine-specific build commands with shared native packaging orchestration and a single version source.
- Added offline checks for both platforms and a manual Windows build workflow.

Previously released binaries are separate artifacts and do not change when the source is refactored. Windows and macOS verification status is visible in GitHub Actions; native packaging must still be validated before each new binary release.
