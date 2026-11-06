# Linux Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ClipFlow runs on Linux (Ubuntu 22.04+ x86-64 / Ubuntu 24.04+ ARM64, Fedora 40+, x86-64 and ARM64) with the same features as Windows/macOS, shipped as a Qt Installer Framework `.run` plus a portable `tar.gz`.

**Architecture:** Linux branches go next to the existing Windows/macOS ones in `src/clipflow/infrastructure` (platform, keep-awake, auth) and in a few `ui` spots. They are selected by `sys.platform == 'linux'` and are testable on any OS by patching the system value. Packaging adds `packaging/linux/` (PyInstaller spec and QtIFW installer) and a `linux` branch in `scripts/build.py`. CI gains Ubuntu jobs.

**Tech Stack:** Python 3.12, PySide6 6.10.3 / QtWebEngine, keyring 25.7 (SecretService backend via its own `SecretStorage` dependency on Linux), cryptography Fernet, PyInstaller 6, Qt Installer Framework 4.x, GitHub Actions `ubuntu-22.04` / `ubuntu-24.04-arm`.

**Spec:** `docs/superpowers/specs/2026-11-02-linux-platform-design.md`

## Global Constraints

- Supported: Ubuntu 22.04+ x86-64 / Ubuntu 24.04+ ARM64 and Fedora 40+; architectures `x86_64` and `aarch64` (`arm64` normalizes to `aarch64`); any other architecture is refused.
- Linux data directory: `$XDG_DATA_HOME/ClipFlow` when `XDG_DATA_HOME` is absolute, else `~/.local/share/ClipFlow`; `CLIPFLOW_DATA_DIR` keeps priority.
- Install directory: `~/.local/opt/ClipFlow`, without root. Uninstall never touches the data directory.
- Package ELF files must not require `GLIBC_` symbols newer than 2.35 on x86-64, or 2.39 on ARM64 (owner-approved 5 November).
- Artifacts: `ClipFlow-<version>-Linux-<arch>-Setup.run`, `ClipFlow-<version>-Linux-<arch>-portable.tar.gz`, `build-report.json`, `package-report.json`, `SHA256SUMS.txt`, `INSTALL.txt` (ru/en).
- Error code for an unavailable secret store: `auth_secret_store_unavailable`; other protection failures stay `auth_protection_failed`. No key or secret appears in any message.
- User-visible text goes through `ui/i18n.py` with both ru and en.
- Windows and macOS behaviour must not change; existing tests stay green on both.
- Tests use `CLIPFLOW_DATA_DIR`; no credentials, cookie stores, keys or machine paths in Git.
- Commits go to `dev` only; every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Validate with `python scripts/check.py` (ruff format/check, pytest and coverage: core lines ≥95%, core branches ≥90%, runtime lines ≥90%).
- No open-source license for ClipFlow's own code; third-party licenses (FFmpeg, Node, QtIFW not shipped) stay intact in `licenses/`.

**Refinement of the spec (same behaviour):** sign-in pages run in a separate process (`auth_process`), so "kept only in memory" works through a *session key*. When Secret Service is unavailable, the main process creates a random Fernet key that lives only in memory. It encrypts with it and passes it to sign-in processes over stdin. After exit the key is gone, so whatever was written is unreadable and counts as signed out. The keyring layer raises `auth_secret_store_unavailable`, and `PlatformServices` catches it and switches to the session key.

## Review Focus

1. **Installing a newer version over an existing one.** QtIFW refuses a non-empty target directory by default. Expected: the update replaces the program and keeps the data. Tested in Task 8 (`installer_smoke` installs twice).
2. **Secret store appears after a run without it.** Files encrypted with an old session key must read as "signed out", with no crash or error dialog. Tested in Task 3 (`test_stale_session_key_files_read_as_signed_out`).
3. **Locked keyring whose unlock prompt the user dismisses** (`secretstorage.exceptions.LockedException`, `PromptDismissedException`, `keyring.errors.KeyringLocked`). Expected: fallback to the session key plus the warning. Tested in Task 3 (`test_locked_or_dismissed_store_is_unavailable`).
4. **Settings copied from Windows with browser `opera_gx` or `safari` chosen.** Expected on Linux: the choice is dropped to the first available browser, with no crash. Tested in Task 5.
5. **Home folder with spaces or Cyrillic** (`/home/кирилл`, `/home/a b`). Expected: the `.desktop` `Exec` quotes the path, the menu entry starts the program, and the data path works. Tested in Task 8 (installer smoke target path with a space and Cyrillic) and Task 2 (data dir).

---

### Task 1: Platform naming, runtime folders, coverage gate, small UI forks

**Files:**
- Modify: `src/clipflow/infrastructure/platform.py` (add `platform_name`)
- Modify: `src/clipflow/ui/bootstrap.py:34-44` (`_binary`)
- Modify: `scripts/package_config.py:12-30` (`resolve_tool`)
- Modify: `scripts/check_coverage.py:56-58` (`foreign_system`)
- Modify: `src/clipflow/ui/themes.py:205` (font)
- Modify: `src/clipflow/ui/window_dialogs.py:110` (reveal label)
- Modify: `src/clipflow/ui/i18n.py:417-418` (new key)
- Test: `tests/unit/test_platform.py`, `tests/ui/test_bootstrap.py`, `tests/integration/test_packaging_config.py`, `tests/ui/test_row_menu.py`, `tests/ui/test_themes.py`

**Interfaces:**
- Produces: `platform_name(system: str = sys.platform) -> str` returning `'windows' | 'macos' | 'linux'` (`win32` → windows, `darwin` → macos, anything starting with `linux` → linux; other values raise `ValueError`). `scripts/package_config.py` gets its own `runtime_folder(system=sys.platform) -> str` with the same mapping (scripts do not import `src`).
- Produces: `foreign_system(system) -> str`, a regex alternation of the other two OS names: `win32` → `(macos|linux)`, `darwin` → `(windows|linux)`, `linux` → `(windows|macos)`. Code marked `# pragma: only linux` is excluded on Windows/macOS.
- Produces: i18n key `row_menu.reveal_linux` = (`'Показать в папке'`, `'Show in folder'`).

- [ ] **Step 1: Write failing tests**
  - `test_platform_name_maps_each_desktop_os`: parametrize `('win32','windows'), ('darwin','macos'), ('linux','linux')`; `platform_name('sunos5')` raises `ValueError`.
  - `test_binary_searches_linux_runtime_folder` (test_bootstrap): monkeypatch `sys.platform='linux'`, create `<root>/.runtime/linux/bin/ffmpeg`, assert `_binary('ffmpeg')` returns it (no `.exe`).
  - `test_resolve_tool_uses_linux_runtime_folder` (test_packaging_config): same for `resolve_tool` with `runtime_folder('linux')`.
  - Extend `test_coverage_leaves_out_code_only_the_other_os_runs` parametrization to `('linux', <windows-marked: excluded>)` and add a `# pragma: only linux` sample: excluded for `win32` and `darwin`, measured for `linux`.
  - `test_reveal_label_on_linux` (test_row_menu): with `sys.platform='linux'` the first menu action text is `'Show in folder'` in English.
  - `test_linux_stylesheet_sets_no_font_family` (test_themes): with `sys.platform='linux'` the stylesheet contains neither `Segoe UI` nor `Helvetica Neue`.
- [ ] **Step 2: Run** `python -m pytest tests/unit/test_platform.py tests/ui/test_bootstrap.py tests/integration/test_packaging_config.py tests/ui/test_row_menu.py tests/ui/test_themes.py -q`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement.** `_binary` and `resolve_tool` use the runtime folder name; `.exe` only on Windows. The theme passes `font_family` per OS and omits the `font-family` declaration on Linux (keep Windows/macOS output byte-identical). `window_dialogs` picks `row_menu.reveal` / `reveal_windows` / `reveal_linux`.
- [ ] **Step 4: Run** the same command. Expected: PASS. Then `python scripts/check.py`: PASS.
- [ ] **Step 5: Commit** `feat: name Linux in runtime folders, coverage gate and row menu`.

### Task 2: Linux data directory

**Files:**
- Modify: `src/clipflow/infrastructure/platform.py:13-18` (`data_directory`)
- Test: `tests/unit/test_platform.py`

**Interfaces:**
- Consumes: `platform.SYSTEM` (module constant tests monkeypatch).
- Produces: `data_directory() -> Path`, unchanged signature.

- [ ] **Step 1: Write failing tests** (monkeypatch `platform.SYSTEM='linux'`, `CLIPFLOW_DATA_DIR` unset, `Path.home()` → tmp):
  - `test_linux_data_dir_uses_absolute_xdg_data_home`: `XDG_DATA_HOME=<tmp>/xdg` → `<tmp>/xdg/ClipFlow`.
  - `test_linux_data_dir_ignores_relative_xdg_data_home`: `XDG_DATA_HOME='rel/x'` → `<home>/.local/share/ClipFlow`.
  - `test_linux_data_dir_defaults_to_local_share`: no XDG → `<home>/.local/share/ClipFlow`.
  - `test_linux_data_dir_accepts_cyrillic_and_space_home`: home `<tmp>/кирилл a` → `<that>/.local/share/ClipFlow`.
  - `test_explicit_data_dir_wins_on_linux`: `CLIPFLOW_DATA_DIR` set → that path.
- [ ] **Step 2: Run** `python -m pytest tests/unit/test_platform.py -q`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement** the Linux branch before the Windows fallback.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat: store Linux data under XDG data home`.

### Task 3: Secret Service key with session-key fallback and warning

**Files:**
- Create: `src/clipflow/infrastructure/linux_secrets.py`
- Modify: `src/clipflow/infrastructure/platform.py` (`PlatformServices.__init__`, `protect`, new `secrets_persistent`)
- Modify: `src/clipflow/infrastructure/auth.py` (`NativeAuthGateway.__init__`, `sign_in` Popen around line 305, new `secrets_persistent`)
- Modify: `src/clipflow/infrastructure/auth_process/__main__.py` (`_parser`, `main`)
- Modify: `src/clipflow/ui/accounts.py` (`AccountsPage.__init__`, `refresh`)
- Modify: `src/clipflow/ui/i18n.py` (new key)
- Test: `tests/unit/test_linux_secrets.py` (new), `tests/unit/test_platform.py`, `tests/ui/test_accounts.py`, `tests/integration/test_entrypoint_parity.py` (auth process args)

**Interfaces:**
- Produces in `linux_secrets.py`:
  - `class SecretStoreUnavailable(OSError)`, constructed as `SecretStoreUnavailable('auth_secret_store_unavailable')`.
  - `fernet_key(service: str, account: str, *, create: bool, backend=None) -> str | None`. Returns the stored key, or creates and stores a new `Fernet.generate_key()` when `create` is true and none exists. Returns `None` when absent and `create` is false. `backend` defaults to `keyring.backends.SecretService.Keyring()`. Any `ImportError`, `keyring.errors.KeyringError` (includes `NoKeyringError`, `KeyringLocked`, `InitError`), `secretstorage.exceptions.SecretStorageException` (includes `LockedException`, `PromptDismissedException`), `jeepney` D-Bus errors or `OSError` while loading or using the backend raises `SecretStoreUnavailable`. The original exception is not chained into the message (`from None`).
- Produces in `PlatformServices`:
  - `__init__(self, data_dir=None, session_key: bytes | None = None)`. An explicit `session_key` (from the parent process) means "do not touch the store; use this key".
  - `session_key: bytes | None`: set when running on the fallback.
  - `protect(data, decrypt=False)`. Linux branch: Fernet with the key from `fernet_key(*self.key_namespace(), create=not decrypt)`. On `SecretStoreUnavailable` it switches to `self.session_key` (generated once with `Fernet.generate_key()` if `None`). Decrypting with no stored key, and any other failure, → `OSError('auth_protection_failed')` as today.
  - `secrets_persistent(self) -> bool`: `True` on Windows/macOS. On Linux: `False` if `session_key` is set, else probe `fernet_key(..., create=False)` once (cache the result); `SecretStoreUnavailable` → switch to a session key and return `False`.
- Produces in `NativeAuthGateway`: `secrets_persistent(self) -> bool` delegating to `self.platform`. When `self.platform.session_key` is set, the sign-in `Popen` adds `--session-key-stdin`, uses `stdin=subprocess.PIPE`, writes `key + b'\n'` and closes stdin.
- Produces in `auth_process.__main__`: flag `--session-key-stdin`; `main` reads one line from `sys.stdin.buffer`, strips it and builds `PlatformServices(root, session_key=...)` for the window and session store.
- Produces i18n key `accounts.secret_store_unavailable` = (`'Не найдено хранилище паролей (GNOME Keyring или KWallet) или оно заблокировано. Данные входа не сохранятся после закрытия ClipFlow.'`, `'No password store (GNOME Keyring or KWallet) was found, or it is locked. Sign-in data will not be kept after ClipFlow closes.'`).
- Produces in `AccountsPage`: attribute `secret_warning: QLabel` (plain text, word-wrapped, hidden by default). `refresh()` shows it with that text when `presenter.auth_gateway` exists and `gateway.secrets_persistent()` is false.

- [ ] **Step 1: Write failing tests** in `tests/unit/test_linux_secrets.py` with a fake backend object (`get_password`, `set_password`):
  - `test_creates_and_returns_key_when_missing`: `create=True` stores a 44-character urlsafe key and returns it; a second call returns the same key.
  - `test_returns_none_without_create`.
  - `test_locked_or_dismissed_store_is_unavailable`: the backend raises `keyring.errors.KeyringLocked`, then a `secretstorage.exceptions.PromptDismissedException`-like `SecretStorageException` subclass, then `OSError` → each raises `SecretStoreUnavailable` with `str(e) == 'auth_secret_store_unavailable'` and `e.__cause__ is None`. (Import secretstorage via `pytest.importorskip` only for that case; the keyring and OSError cases run everywhere.)
  - `test_missing_backend_is_unavailable`: a `backend` factory raising `ImportError` → `SecretStoreUnavailable`.
- [ ] **Step 2: Write failing tests** in `tests/unit/test_platform.py` (monkeypatch `platform.SYSTEM='linux'` and `linux_secrets.fernet_key`):
  - `test_linux_protect_round_trips_with_stored_key`.
  - `test_linux_protect_falls_back_to_session_key`: `fernet_key` raises `SecretStoreUnavailable` → `protect` round-trips, `session_key` is set, `secrets_persistent()` is `False`.
  - `test_stale_session_key_files_read_as_signed_out`: encrypt with `PlatformServices(session_key=k1)`, write via `atomic_protected`, then `load_protected` with `PlatformServices(session_key=k2)` returns `None`.
  - `test_linux_protect_errors_hide_secrets`: corrupt token → `OSError('auth_protection_failed')`, and the message does not contain the key.
  - `test_secrets_persistent_true_on_windows_and_macos`.
- [ ] **Step 3: Write failing tests** for wiring:
  - `test_sign_in_passes_session_key_over_stdin` (tests for `NativeAuthGateway.sign_in`, monkeypatched `subprocess.Popen`): with `platform.session_key=b'k'` the args contain `--session-key-stdin`, `stdin=PIPE`, and `b'k\n'` is written. Without a session key: no flag, no stdin pipe.
  - `test_auth_process_reads_session_key_from_stdin` (entrypoint parity): `_parser().parse_args(['--youtube-login','--session-key-stdin'])` sets the flag, and the helper that builds platform services uses the stdin line.
  - `test_accounts_warns_when_secrets_not_persistent` (test_accounts): fake gateway `secrets_persistent() -> False` → `secret_warning.isVisible()` (after `show`) and English text equals the en string; `True` → hidden.
- [ ] **Step 4: Run** `python -m pytest tests/unit/test_linux_secrets.py tests/unit/test_platform.py tests/ui/test_accounts.py tests/integration/test_entrypoint_parity.py -q`. Expected: the new tests FAIL.
- [ ] **Step 5: Implement** per the Interfaces block. Mark Linux-only lines `# pragma: only linux` only where they cannot run under the fakes on other OSes (the backend import default).
- [ ] **Step 6: Run** the same command and `python scripts/check.py`. Expected: PASS.
- [ ] **Step 7: Commit** `feat: keep Linux sign-in keys in Secret Service with session fallback`.

### Task 4: Keep awake through systemd-inhibit

**Files:**
- Modify: `src/clipflow/infrastructure/keep_awake.py`
- Test: `tests/unit/test_keep_awake.py`

**Interfaces:**
- Consumes: `KeepAwake(run=..., kernel32=..., system=...)` (existing).
- Produces: on `system` starting with `linux`, `hold()` runs exactly `['systemd-inhibit', '--what=sleep:idle', '--who=ClipFlow', '--why=Downloads in progress', '--mode=block', 'tail', f'--pid={os.getpid()}', '-f', '/dev/null']` with stdout/stderr `DEVNULL`. `release()` terminates or kills it exactly as for `caffeinate`.

- [ ] **Step 1: Write failing tests:** `test_linux_hold_runs_systemd_inhibit_bound_to_pid` (fake `run` records args), `test_linux_release_terminates_inhibitor`, `test_linux_missing_systemd_inhibit_is_silent` (fake `run` raises `FileNotFoundError` → no exception, a second `hold` after `release` retries).
- [ ] **Step 2: Run** `python -m pytest tests/unit/test_keep_awake.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the Linux branch next to the `darwin` one.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat: hold sleep inhibitor on Linux during downloads`.

### Task 5: Browsers for cookies on Linux

**Files:**
- Modify: `src/clipflow/domain/models.py:209-222` (add `browsers_for`)
- Modify: `src/clipflow/infrastructure/auth.py:199-217` (`browser_source`), `configure_getcourse` validation
- Modify: `src/clipflow/ui/accounts.py:115-125` (combo built from `browsers_for`)
- Test: `tests/unit/test_platform.py` or a new `tests/unit/test_browsers.py`, `tests/ui/test_accounts.py`

**Interfaces:**
- Produces: `browsers_for(system: str = sys.platform) -> tuple[str, ...]`. It is `BROWSERS` without `opera_gx` and `safari` on Linux, and unchanged elsewhere. (Safari is added here because it has no Linux build and yt-dlp cannot read it there. This follows the spec's "no non-working choices" rule; the owner sees it in the plan review.)
- Produces: `browser_source('yandex')` on Linux → `('chrome', str(Path.home() / '.config/yandex-browser'))`.
- Produces: a stored GetCourse profile whose `browser` is not in `browsers_for()` loads with the browser reset to `browsers_for()[0]`, without an error. `configure_getcourse(..., browser=<not available>)` raises `MediaFailure('auth_invalid_settings')`.

- [ ] **Step 1: Write failing tests:** `test_linux_browser_list_has_no_opera_gx_or_safari`, `test_windows_and_macos_browser_lists_unchanged`, `test_linux_yandex_cookie_folder`, `test_saved_unavailable_browser_resets_on_linux`, `test_configure_rejects_unavailable_browser_on_linux`, `test_accounts_combo_lists_linux_browsers` (combo item data equals `browsers_for('linux')` with `sys.platform` patched).
- [ ] **Step 2: Run** the new tests. Expected: FAIL.
- [ ] **Step 3: Implement.** Find where the saved GetCourse payload's `browser` is read (`options_for` / `status` in `auth.py`) and apply the reset there.
- [ ] **Step 4: Run** the tests and `python scripts/check.py`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: offer only Linux-capable browsers for cookies`.

### Task 6: Sign-in window sandbox on restricted Ubuntu

**Files:**
- Modify: `src/clipflow/infrastructure/auth_process/__main__.py` (new helper, call in `main` before importing PySide6)
- Test: `tests/integration/test_entrypoint_parity.py` or a new `tests/unit/test_auth_sandbox.py`

**Interfaces:**
- Produces: `sandbox_environment(environ: dict, system: str = sys.platform, flag: Path = Path('/proc/sys/kernel/apparmor_restrict_unprivileged_userns')) -> dict`. It returns a copy of `environ` with `QTWEBENGINE_DISABLE_SANDBOX='1'` only when `system` starts with `linux` and the flag file's stripped content is `'1'`. A missing or unreadable file, or `'0'`, leaves the environment unchanged. `main` applies the result to `os.environ` before any PySide6 import. The main app process never calls it.

- [ ] **Step 1: Write failing tests:** parametrize the flag content `'1\n'` → disabled, `'0\n'` → unchanged, missing file → unchanged, `system='win32'` with `'1'` → unchanged. Also check that the input dict is not mutated.
- [ ] **Step 2: Run** the tests. Expected: FAIL.
- [ ] **Step 3: Implement** and call it at the top of `main` after `_launch`.
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat: disable WebEngine sandbox only where Ubuntu restricts user namespaces`.

### Task 7: Linux package configuration (pure functions and spec)

**Files:**
- Modify: `scripts/package_config.py`
- Create: `packaging/linux/ClipFlow.spec`
- Test: `tests/integration/test_packaging_config.py`

**Interfaces:**
- Produces in `package_config.py`:
  - `linux_arch(machine: str) -> str`: `x86_64`/`amd64` → `x86_64`, `aarch64`/`arm64` → `aarch64`, otherwise `ValueError`.
  - `linux_artifact_names(version: str, arch: str) -> dict[str, str]` with keys `setup` (`ClipFlow-<v>-Linux-<arch>-Setup.run`) and `portable` (`ClipFlow-<v>-Linux-<arch>-portable.tar.gz`).
  - `GLIBC_LIMIT = (2, 35)`; `max_glibc(objdump_text: str) -> tuple[int, int] | None` parses the `GLIBC_<major>.<minor>[.<patch>]` versions in `objdump -T` output and returns the highest major/minor; `glibc_violations(root: Path, run=subprocess.run) -> list[str]` runs `objdump -T` on every file starting with `b'\x7fELF'` and returns the relative paths whose `max_glibc` exceeds `GLIBC_LIMIT`.
  - `desktop_entry(exec_path: str, icon: str = 'clipflow') -> str`: `[Desktop Entry]`, `Type=Application`, `Name=ClipFlow`, `Comment=` (en), `Comment[ru]=`, `Exec="<path>"` (inner `"`, `` ` ``, `$`, `\` escaped per the Desktop Entry spec), `Icon=clipflow`, `Terminal=false`, `Categories=AudioVideo;Network;`, `StartupWMClass=ClipFlow`. The build writes its output with a `@TargetDir@` placeholder into the QtIFW package (Task 8).
  - `spec_inputs(root, 'linux')` adds `keyring.backends.SecretService` to hidden imports and copies `SecretStorage` and `jeepney` metadata.
- Produces `packaging/linux/ClipFlow.spec`: the Windows spec minus `version`/`.ico`, plus `icon` omitted. Output folder `ClipFlow/` with executable `ClipFlow`.

- [ ] **Step 1: Write failing tests:** `test_linux_arch_normalizes_and_refuses` (parametrized), `test_linux_artifact_names`, `test_max_glibc_reads_highest_version` (sample text containing `GLIBC_2.17`, `GLIBC_2.34`, `GLIBC_2.2.5`, `GLIBC_PRIVATE` → `(2, 34)`; no versions → `None`), `test_glibc_violations_lists_only_newer_elf` (tmp files: one ELF with fake run output `GLIBC_2.38`, one ELF with `2.35`, one text file → only the first), `test_desktop_entry_quotes_space_and_cyrillic_path` (`/home/кирилл a/.local/opt/ClipFlow/ClipFlow` → `Exec="/home/кирилл a/.local/opt/ClipFlow/ClipFlow"`; a path with `$` is escaped), `test_linux_spec_inputs_include_secret_service` (runs where PyInstaller is installed; skip otherwise like the neighbouring spec tests).
- [ ] **Step 2: Run** `python -m pytest tests/integration/test_packaging_config.py -q`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement** the functions and the spec file.
- [ ] **Step 4: Run** the same command and `python scripts/check.py`. Expected: PASS.
- [ ] **Step 5: Commit** `build: Linux package configuration`.

### Task 8: QtIFW installer, build wiring and package smoke

**Files:**
- Create: `packaging/linux/installer/config/config.xml`, `packaging/linux/installer/config/controller.qs`, `packaging/linux/installer/packages/com.clipflow.app/meta/package.xml`, `packaging/linux/installer/packages/com.clipflow.app/meta/installscript.qs`
- Create: `scripts/installer_smoke.py`
- Modify: `scripts/build.py` (`main`, new helper `installer_creator()`)
- Modify: `scripts/package_smoke.py` (`clean_environment`, `inspect_package`)
- Modify: `INSTALL.txt` (Linux section ru/en)
- Test: `tests/integration/test_packaging_config.py`, `tests/ui/test_package_self_test.py` (if it covers `package_smoke`)

**Interfaces:**
- Consumes: Task 7 functions.
- Produces `config.xml`: `Name`/`Title` ClipFlow, `Version` written by `build.py`, `TargetDir` = `@HomeDir@/.local/opt/ClipFlow`, `RunProgram` = `@TargetDir@/ClipFlow`, `StartMenuDir` unused, `MaintenanceToolName` = `maintenancetool`, `ControlScript` = `controller.qs`, `InstallerApplicationIcon`/`WizardStyle` set, no `AdminTargetDir`.
- Produces `controller.qs`: when the chosen target directory already holds `maintenancetool`, it runs it with `purge --confirm-command` (QtIFW 4 CLI) before installing, so a new version replaces the old one. The data directory is never touched.
- Produces `installscript.qs`: computes `dataHome` = `XDG_DATA_HOME` if absolute, else `@HomeDir@/.local/share`. It adds the operations `CreateDesktopEntry` (`<dataHome>/applications/clipflow.desktop`, content from `desktop_entry` with `@TargetDir@`), `Copy` of `clipflow.png` to `<dataHome>/icons/hicolor/256x256/apps/clipflow.png`, a second desktop entry `clipflow-uninstall.desktop` (`Exec="@TargetDir@/maintenancetool"`, `Name=Uninstall ClipFlow`, `Name[ru]=Удалить ClipFlow`), and `Execute` of `update-desktop-database <dataHome>/applications` with `errormessage` suppressed when the tool is missing. QtIFW undoes these on uninstall.
- Produces `installer_creator() -> str`: `QTIFW_BINARYCREATOR`, else `binarycreator` on `PATH`, else `RuntimeError('Set QTIFW_BINARYCREATOR or install Qt Installer Framework 4; --portable-only skips installer')`.
- Produces `build.py` Linux branch: `system='linux'`, `arch = linux_arch(platform.machine())`, `executable = output/'ClipFlow'/'ClipFlow'`. After the PyInstaller run, `glibc_violations` non-empty → `RuntimeError` listing the files. Smoke, then `tar.gz` (`tarfile`, mode preserved, root `ClipFlow/`). Unless `--portable-only`: copy `ClipFlow/` and `assets/icons/clipflow.png` (resized to 256×256 with Pillow if needed) into a staged QtIFW `packages/com.clipflow.app/data`, write `config.xml` with the version, run `binarycreator --offline-only -c config/config.xml -p packages <setup.run>`, then `installer_smoke`. `INSTALL.txt` is copied to the output. The reports and `SHA256SUMS.txt` are as today; `launch_services_mac27_verified` stays only for macOS.
- Produces `scripts/installer_smoke.py --installer PATH --work DIR`: with `QT_QPA_PLATFORM=minimal` and a temporary `XDG_DATA_HOME`, it
  1. installs into `DIR/a b/кирилл/ClipFlow` (`--root … --accept-licenses --default-answer --confirm-command install`);
  2. checks that `applications/clipflow.desktop` exists, that its `Exec` (unquoted) points to an existing executable, and the icon file;
  3. runs `package_smoke.run` on the installed executable;
  4. installs the same `.run` again over it (update path) and checks that a marker file in a separate `CLIPFLOW_DATA_DIR` survives;
  5. runs `maintenancetool purge --confirm-command`: the target dir and both desktop files are gone and the data dir is untouched;
  6. writes `installer-report.json` with `passed: true`.
  Any failure raises `RuntimeError` naming the step.
- `package_smoke.clean_environment` on Linux: keeps `DISPLAY`, `WAYLAND_DISPLAY`, `XDG_RUNTIME_DIR` and `DBUS_SESSION_BUS_ADDRESS`, and sets `QT_QPA_PLATFORM` to `offscreen` when neither display variable is present, otherwise does not set it. `inspect_package` root on Linux is `executable.parent`; `.exe` is appended only on Windows.

- [ ] **Step 1: Write failing tests** (pure, run on any OS):
  - `test_linux_smoke_environment_offscreen_without_display` and `..._keeps_display` (`clean_environment` with `os.name` and display vars patched).
  - `test_installer_config_files_are_valid_xml_with_home_target` (parse `config.xml` and `package.xml`: `TargetDir == '@HomeDir@/.local/opt/ClipFlow'`, `MaintenanceToolName == 'maintenancetool'`, `ControlScript == 'controller.qs'`, no `AdminTargetDir`).
  - `test_installscript_targets_xdg_data_home_and_icon` (text assertions: `XDG_DATA_HOME`, `CreateDesktopEntry`, `hicolor/256x256/apps/clipflow.png`, `clipflow-uninstall.desktop`).
  - `test_controller_purges_existing_installation` (text: `maintenancetool`, `purge`).
  - `test_build_refuses_unknown_linux_arch` (`main` with `sys.platform='linux'`, `platform.machine()='riscv64'` → parser error).
  - `test_installer_creator_requires_binarycreator` (no env/PATH → `RuntimeError` text).
- [ ] **Step 2: Run** `python -m pytest tests/integration/test_packaging_config.py tests/ui/test_package_self_test.py -q`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement** the files and the build branch.
- [ ] **Step 4: Run** the same command and `python scripts/check.py`. Expected: PASS. (The real `.run` build and `installer_smoke` run in Task 9's CI.)
- [ ] **Step 5: Commit** `build: Linux QtIFW installer with install, update and uninstall smoke`.

### Task 9: CI for Linux checks and packages

**Files:**
- Modify: `.github/workflows/check.yml`
- Modify: `.github/workflows/build.yml`
- Create: `scripts/linux_tools.py` (downloads and verifies pinned FFmpeg, Node and QtIFW for the build job)
- Create: `tests/platform/test_secret_service.py`
- Test: `tests/integration/test_packaging_config.py` (pins)

**Interfaces:**
- Produces `scripts/linux_tools.py --arch {x86_64,aarch64} --dest DIR`: a `PINS` dict per arch with `url` and `sha256` for (a) a BtbN FFmpeg static GPL build of a fixed `autobuild-YYYY-MM-DD` tag (`linux64` / `linuxarm64`) and (b) Node LTS `v22.x` `linux-x64` / `linux-arm64` `.tar.xz`. Values are copied from upstream `checksums.sha256` / `SHASUMS256.txt` at implementation time and the tag/version recorded in `THIRD-PARTY-NOTICES.md`. It extracts `ffmpeg`, `ffprobe` and `node` to `DIR/bin`, stores their licenses in `work/package-licenses/`, and on a SHA mismatch raises `RuntimeError` and deletes the download. For `x86_64` it also fetches the pinned official QtIFW 4.x Linux x64 installer, runs it headless into `DIR/qtifw`, and prints `binarycreator`'s path.
- `check.yml`: matrix adds `ubuntu-22.04`. A Linux step runs `sudo apt-get install -y` Qt runtime libs (`libegl1 libgl1 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1 libxcb-shape0 libxcb-randr0 libxcb-render-util0 libxcb-xinerama0 libfontconfig1 libdbus-1-3 libnss3 libxcomposite1 libxdamage1 libxrandr2 libxtst6 libasound2`), plus `ffmpeg gnome-keyring dbus-x11`. Offline checks are as today. New Linux-only step: `dbus-run-session -- sh -c 'echo -n test | gnome-keyring-daemon --unlock --components=secrets && python -m pytest tests/platform/test_secret_service.py -q'` with `CLIPFLOW_SECRET_SERVICE_NATIVE=1`.
- `tests/platform/test_secret_service.py`: skips unless Linux and `CLIPFLOW_SECRET_SERVICE_NATIVE=1`. `test_real_store_round_trip_and_cleanup` (`fernet_key('ClipFlow Tests', <unique>, create=True)` twice gives the same key; deleting via the backend removes it; a `finally` always deletes). `test_no_bus_is_unavailable` (with `DBUS_SESSION_BUS_ADDRESS` set to an invalid path in a subprocess → `SecretStoreUnavailable`).
- `build.yml`: `target` options add `linux`. The matrix for `all` adds `ubuntu-22.04` and `ubuntu-24.04-arm`; `linux` alone selects both. Linux steps: the apt libs above plus `binutils`, then `python scripts/linux_tools.py --arch <arch> --dest .runtime/linux`, setting `CLIPFLOW_BIN_DIR` and `QTIFW_BINARYCREATOR`. ARM64 only: restore cache `qtifw-<version>-aarch64`; on a miss, build QtIFW `<version>` from source against a static Qt per the QtIFW README, then save the cache. Build with `QT_QPA_PLATFORM=offscreen python scripts/build.py`. Artifact paths add `outputs/**/ClipFlow-*-Linux-*-Setup.run`, `outputs/**/ClipFlow-*-Linux-*-portable.tar.gz`, `outputs/**/installer-report.json`, `outputs/**/INSTALL.txt`.

- [ ] **Step 1: Write failing tests:** `test_linux_tool_pins_are_complete` (each arch has ffmpeg and node with a 64-hex `sha256` and an `https://` URL; x86_64 has qtifw), `test_linux_tools_rejects_checksum_mismatch` (fake downloader writing wrong bytes → `RuntimeError`, file removed), and the secret service test file.
- [ ] **Step 2: Run** `python -m pytest tests/integration/test_packaging_config.py tests/platform/test_secret_service.py -q`. Expected: the pin tests FAIL and the secret service tests SKIP on Windows.
- [ ] **Step 3: Implement** the script and the workflows.
- [ ] **Step 4: Run** `python scripts/check.py`. Expected: PASS. Commit `ci: Linux checks, Secret Service test and Linux package builds`, push `dev`.
- [ ] **Step 5: Verify on GitHub:** `gh run watch` on Checks for the pushed commit. Expected: all three OS jobs green. Then `gh workflow run build.yml -f target=linux --ref dev` and watch. Expected: both Linux jobs upload `.run`, `tar.gz` and reports. If `ubuntu-24.04-arm` is unavailable to the repository, record it as unavailable (not success) and report it to the owner. Fix failures in follow-up commits, never by skipping a check.

### Task 10: Docs, project rules and QA checklist

**Files:**
- Create: `docs/LINUX-QA.md`
- Modify: `AGENTS.md`, `docs/PROJECT-MEMORY.md`, `README.md` (platform list and Linux install), `THIRD-PARTY-NOTICES.md` (FFmpeg/Node Linux builds)
- Test: `tests/integration/test_packaging_config.py` if it already asserts README/notice content; otherwise none

**Interfaces:**
- `docs/LINUX-QA.md`: the spec's nine checklist sections verbatim in meaning, as a table with columns `Check | Fedora 44 x86-64 (owner) | Ubuntu ARM64 (Parallels on Mac) | Date | Build commit | Notes`. It includes the Parallels Ubuntu ARM64 preparation, SHA256 verification commands, the `.tar` wrapper experiment for item 2, and the rule "until filled: built and CI-verified, not manually verified".
- `AGENTS.md`: Linux is the third platform; data in `~/.local/share/ClipFlow`; merge `dev` → `main` only after Windows, macOS **and** Linux checks pass for the exact commit; Linux packages build on Linux; manual Linux acceptance is tracked in `docs/LINUX-QA.md` and never inferred from CI.
- `PROJECT-MEMORY.md`: Linux milestone state with links to the spec, plan and checklist; the open questions (`.tar` wrapper, ARM runner availability, with the result from Task 9).

- [ ] **Step 1: Write** the documents.
- [ ] **Step 2: Run** `python scripts/check.py`. Expected: PASS.
- [ ] **Step 3: Commit** `docs: Linux QA checklist and project rules for three platforms`, push `dev`, and confirm Checks are green on all three OS for the final commit.
- [ ] **Step 4: Report** to the owner: commits, check results per OS, Linux build artifacts (or ARM unavailability), and what remains manual (Fedora 44 x86-64 by the owner, Ubuntu ARM64 on the Mac). Then pause.


## Owner-approved implementation refinements — 5 November 2026

ARM64 minimum is Ubuntu24.04/glibc2.39; x86-64 remains Ubuntu22.04/glibc2.35.
Official PySide6 6.10.3 ARM64 wheels require glibc2.39. Official QtIFW4.8.1 x64 binaries are pinned. The ARM64 binary requires obsolete
libtiff.so.5 on Ubuntu24; build QtIFW4.11.0 against static Qt6.7.2 from pinned
vendor source archives, cache verified tools, and run full native installer smoke.
Temporary authentication must not replace durable profiles: use a private RAM-backed
/dev/shm directory, shared with the auth child via stdin along with its ephemeral key.
