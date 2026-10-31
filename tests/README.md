# Regression checks

Run `python scripts/check.py` from the repository root using the configured Python 3.12 environment. It checks style with ruff, then runs every test with Qt offscreen in isolated temporary profiles (`CLIPFLOW_DATA_DIR`) without real account login, and enforces the coverage gates: core 95% lines / 90% branches, whole runtime 90% lines, including code run in child processes.

Layout: `unit` (domain rules, scheduler, providers with fixtures), `integration` (localhost HTTP, FFmpeg/FFprobe, SQLite, Instagram transport), `ui` (real Qt Widgets), `platform` (clipboard, protected sign-in, process lifecycle). Shared fixtures live in `conftest.py`; helpers in `support/` and `helpers.py`; test modules never import each other.

GitHub Actions runs the same suite on Windows and macOS, plus native clipboard/DPI and sign-in steps. Actual service access requires separate network checks and, for private content, a user account. Details: `docs/TESTING.md`.
