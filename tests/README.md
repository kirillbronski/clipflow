# Regression checks

Run `python scripts/check.py` from the repository root using the configured Python 3.12 environment. Checks run in isolated temporary profiles without real account login.

Coverage: queue state and stale run events; stable row geometry; progress throttling; Instagram photo downloads and description TXT/MD; file deletion; three service tabs, quality probes and auto-download; native paths and Windows DPAPI round-trip on Windows.

GitHub Actions runs the same suite on Windows and macOS. Embedded Qt login tests are also run by the packaging script. Actual service access requires separate network checks and, for private content, a user account.
