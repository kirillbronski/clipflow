# ClipFlow unified project

This repository is the authoritative shared source for Windows and macOS. Edit `src/clipflow` once; keep platform behavior in `src/clipflow/infrastructure` and packaging files in `packaging/`.

For initial Windows setup after the unification, also read `docs/WINDOWS-CODEX-HANDOFF.md`; it records the migration state, local setup steps and remaining native-build checks. Fetch current repository instructions rather than assuming its historical verification commit is the latest source.

Read `docs/PROJECT-MEMORY.md` for the current Qt migration state, approved spec and implementation plan. Keep milestone notes and copies of specs/plans in the owner's `Agents/ClipFlow` folder when it is available locally; resolve its path on each computer. That folder is a portable continuation pack, not a checkout or a credentials store. Do not apply another project's instructions merely because it shares the parent Agents directory.

Owner execution preference: pause after each authorized task. Current Mac task (29 October): restore the approved screenshot composition with per-service brand-like accents; save memory/snapshot then pause before remaining T16a acceptance. On 29 October owner explicitly authorized all Windows T16 work while no Mac is available; Mac acceptance is a separate OPEN T16a (docs/MAC-T16A.md). Owner reconfirmed C:/Users/Kirill/PycharmProjects/ClipFlow for ongoing work despite the old Drive-folder instructions. Old Drive Windows stays read-only. Delivery preference D:/Gdrive/ClipFlow. Do not infer Mac acceptance from Windows or CI15.

- Start each session with `git status`, inspect the branch/upstream and read these instructions. Never overwrite unrelated user changes.
- Development branch is `dev`; stable branch is `main`. Before edits, fetch, switch to `dev` on a clean checkout and pull with `--ff-only`. Make all ongoing changes in `dev`, never directly in `main`. Do not overwrite or discard local work to switch branches.
- Push development commits to `origin/dev`. Merge `dev` into `main` only after local checks and GitHub Checks for BOTH Windows and macOS pass for the exact proposed commit; run relevant native/package/manual checks when the change requires them. A pending, failed or unavailable check is not success. Prefer a `dev` → `main` pull request; attach created PRs to the Codex chat. Never bypass a failed check. Return the working checkout to `dev` after merging.
- Validate with the checkout's Python 3.12 environment: `python scripts/check.py`. Build with `python scripts/build.py` on the target OS.
- All Windows settings, GetCourse credentials and sessions now use LocalAppData/ClipFlow; macOS data stays in Library/Application Support/ClipFlow. Before first Windows launch after the path change, locate and back up the previous app's data directory, then use scripts/migrate_windows_data.py --source PATH to copy settings/GetCourse without overwriting current files or deleting originals. Never rename or delete legacy data blindly.
- Keep user credentials, cookie stores, keys and machine paths out of Git. Use `CLIPFLOW_DATA_DIR` for all tests.
- Instagram requests must share the pacing/cooldown policy in `docs/INSTAGRAM-RATE-LIMITS.md`, including profile discovery, individual posts and automatic probes. A network timeout is not a request interval; never reset the rate budget for each job or turn HTTP 429 into success.
- Commit coherent verified changes with a clear message; push authorized completed work to the corresponding remote branch. Report commit and check results. Never force-push shared history.
- GUI/network mock tests do not replace packaged checks. Verify embedded auth and installer integrity before a release. Clearly report which OS was actually tested.
- Keep one installed macOS app. After verified packaging/install, unregister and remove temporary app copies, preserving the DMG/ZIP.
- The legacy Google Drive `Windows` project is a read-only baseline during migration. Do not edit, rename or delete it. Drive holds release archives/backups; do not sync `.git` or `.venv` through Drive.
- Legacy 1.8.4 installers predate the refactor. New 1.8.5 builds use the unified source; always record the source commit and actual native/package verification instead of inferring a build's contents from its version number.

The owner does not want an open-source license for ClipFlow's own code. Do not add MIT/GPL/Apache or change this policy without explicit owner authorization. Keep third-party licenses intact.
