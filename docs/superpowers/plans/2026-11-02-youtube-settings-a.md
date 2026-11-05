# Настройки как в 4K, часть 5а — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Семь настроек из 4K в новых разделах «Дополнительные», «Соединение», «Уведомления»: пропуск скачанного, `.m3u8`, субтитры, запрет сна, скрытие скачанного, скорость, уведомление о завершении.

**Architecture:** Поля в `AppSettings`; то, что влияет на загрузку (скорость, субтитры), идёт в исполнитель как неизменяемое `DownloadPreferences` в `ExecutionContext`; пропуск — флаг планировщика; `.m3u8`, сон и уведомление — презентер по событиям; скрытие — флаг `QueueFilter`.

**Tech Stack:** Python 3.12, PySide6, yt-dlp, pytest + pytest-qt, ruff 0.17.3.

**Spec:** `docs/superpowers/specs/2026-11-02-youtube-settings-a-design.md`

## Global Constraints

- Поля `AppSettings` и значения по умолчанию: `skip_downloaded=False`, `playlist_m3u=False`, `subtitles=None` (иначе `'original' | 'ru' | 'en'`), `keep_awake=False`, `hide_completed=False`, `rate_limit=None` (иначе одно из `1, 2, 5, 10` × 1 048 576), `notify_done=False`; файл без поля → значение по умолчанию; неверное значение → настройки по умолчанию.
- Разделы (порядок): «Основные», «Дополнительные» (`☰`), «Соединение» (`◎`), «Уведомления» (`🔔`), «Авторизация», внизу «О программе».
- Тексты (ru / en), ключи `settings_section.advanced` «Дополнительные» / «Advanced», `settings_section.connection` «Соединение» / «Connection», `settings_section.notifications` «Уведомления» / «Notifications»; строки и пояснения — дословно из спецификации (en — перевод по смыслу).
- Ключ «тот же ролик» для пропуска: `(service, canonical_id, format, max_height)`; завершённое задание засчитывается, только если все его `result_files` существуют.
- `.m3u8`: UTF-8, `#EXTM3U`, на трек `#EXTINF:<round(duration) или -1>,<название>` и путь относительно файла списка через `/`; порядок — `playlist.index`; запись атомарная (временный файл + `os.replace`).
- yt-dlp: `ratelimit=<байты/с>`; субтитры — `writesubtitles=True`, `writeautomaticsub=False`, `subtitleslangs=[lang]`, постобработчик `{'key': 'FFmpegEmbedSubtitle'}`; только YouTube и не MP3.
- Уведомление: заголовок «ClipFlow — загрузки завершены» / «ClipFlow — downloads finished», текст «Скачано: N» + «, с ошибкой: M» / «Downloaded: N» + «, failed: M».
- Покрытие: ядро ≥95 % строк / ≥90 % ветвлений, программа ≥90 %.

## Review Focus

1. Плейлист повторили после ошибок — `.m3u8` перезаписан полнее, без дублей строк — тест `test_m3u_rewritten_after_retry` (Task 4).
2. Программа закрыта во время загрузки при включённом запрете сна — защита снята (дочерний `caffeinate` завершён) — тест `test_keep_awake_released_on_shutdown` (Task 5).
3. Очередь «пустеет» на паузе ожидания Instagram — это не завершение, уведомления нет — тест `test_rate_limit_pause_is_not_finished` (Task 6).
4. «Убирать скачанное» включено, а плейлист скачан частично (есть ошибка) — плейлист виден — тест `test_partly_failed_group_stays_visible` (Task 7).
5. Ограничение скорости поменяли посреди загрузки — идущая не меняется, следующая получает новое — тест `test_rate_limit_applies_to_the_next_job` (Task 2).

---

### Task 1: Настройки и разделы

**Files:** Modify `src/clipflow/infrastructure/settings.py`, `src/clipflow/ui/settings_page.py` (`SECTIONS`, три раздела, семь строк), `src/clipflow/ui/i18n.py`. Test: `tests/unit/test_settings_migration.py`, `tests/ui/test_settings_page.py`.

**Interfaces:** Produces поля `AppSettings` из Global Constraints; `SettingsPage.section_buttons` содержит `'advanced'`, `'connection'`, `'notifications'`; атрибуты строк `skip_toggle`, `m3u_toggle`, `subtitles_toggle`, `subtitles_language_box`, `keep_awake_toggle`, `hide_completed_toggle`, `rate_box`, `notify_toggle`; всё сохраняется через `presenter.update_preferences(**{field: value})`.

- [ ] Step 1: тесты — `test_new_settings_round_trip_and_defaults` (все поля; старый файл без них; `rate_limit=12345` → по умолчанию); `test_sections_order` (порядок ключей `section_buttons`); `test_each_new_row_saves` (каждая строка меняет своё поле); `test_subtitle_language_only_when_enabled`.
- [ ] Step 2: запуск → FAIL.
- [ ] Step 3: реализация (субтитры: тумблер вкл. → `subtitles='original'`; выкл. → `None`; список языка меняет значение и виден только при вкл.).
- [ ] Step 4: `pytest tests/unit/test_settings_migration.py tests/ui/test_settings_page.py tests/ui/test_texts.py -q` → passed.
- [ ] Step 5: commit `feat: advanced, connection and notification settings`.

### Task 2: Скорость и субтитры в загрузке

**Files:** Modify `src/clipflow/providers/base.py` (`DownloadPreferences(rate_limit: int | None = None, subtitles: str | None = None)`, `ExecutionContext.preferences: DownloadPreferences = DownloadPreferences()`), `src/clipflow/infrastructure/executor.py` (`ThreadExecutor.preferences`, передаётся в контекст каждой новой работы), `src/clipflow/providers/media.py` (`_options`), `src/clipflow/ui/presenter.py` (обновляет `executor.preferences` при загрузке и смене настроек). Test: `tests/unit/test_media_options.py` (новый), `tests/ui/test_presenter.py`.

- [ ] Step 1: тесты — `test_rate_limit_option`; `test_subtitles_for_youtube_video_only` (MP4 — опции субтитров и постобработчик; MP3 и Instagram — нет); `test_original_language_from_info`; `test_rate_limit_applies_to_the_next_job` (смена настройки после старта: у первой работы прежний контекст, у следующей новый).
- [ ] Step 2: запуск → FAIL.
- [ ] Step 3: реализация.
- [ ] Step 4: `pytest tests/unit tests/integration tests/ui/test_presenter.py -q` → passed.
- [ ] Step 5: commit `feat: speed limit and embedded subtitles`.

### Task 3: Пропуск уже скачанного

**Files:** Modify `src/clipflow/application/scheduler.py` (`Scheduler.skip_downloaded: bool = False`; `_on_discovered`), `src/clipflow/ui/presenter.py` (держит флаг равным настройке). Test: `tests/unit/test_scheduler.py`.

- [ ] Step 1: тесты — `test_skip_downloaded_track_in_new_playlist`; `test_missing_files_or_other_format_are_not_skipped` (удалён файл; `mp3` против `mp4`; другой `max_height`); `test_skip_off_keeps_old_behaviour`.
- [ ] Step 2: запуск → FAIL. Step 3: реализация. Step 4: `pytest tests/unit/test_scheduler.py -q` → passed.
- [ ] Step 5: commit `feat: skip tracks already downloaded`.

### Task 4: Список `.m3u8`

**Files:** Create `src/clipflow/application/playlists.py` (`m3u_text(entries: Sequence[M3uEntry], base: Path) -> str`, `M3uEntry(path: Path, title: str, duration: float | None, index: int)`, `m3u_name(title: str) -> str` — безопасное имя по правилам `domain/paths`), `src/clipflow/infrastructure/playlist_files.py` (`write_m3u(path, text)`, атомарно). Modify `src/clipflow/ui/presenter.py` (после события завершения трека группы-плейлиста YouTube без активных треков при `playlist_m3u` — запись; удаление файлов группы удаляет её `.m3u8`), `src/clipflow/ui/presenter_clearing.py`. Test: `tests/unit/test_playlists.py`, `tests/ui/test_playlist_m3u.py`.

- [ ] Step 1: тесты — `test_m3u_text_order_paths_and_durations` (кириллица, `-1`, «/»); `test_m3u_name_is_safe`; `test_m3u_written_when_playlist_finishes`; `test_m3u_rewritten_after_retry`; `test_no_m3u_when_off_or_folders_disjoint`; `test_deleting_group_files_removes_m3u`.
- [ ] Step 2: запуск → FAIL. Step 3: реализация. Step 4: `pytest tests/unit/test_playlists.py tests/ui/test_playlist_m3u.py tests/unit/test_layers.py -q` → passed.
- [ ] Step 5: commit `feat: m3u8 playlist files`.

### Task 5: Не давать засыпать

**Files:** Create `src/clipflow/infrastructure/keep_awake.py` (`KeepAwake(run=subprocess.Popen, kernel32=None)`: `hold()`, `release()`; macOS — `['caffeinate', '-i', '-w', str(os.getpid())]`, Windows — `SetThreadExecutionState(0x80000000 | 0x00000001)` / `(0x80000000)`; прочие ОС — ничего). Modify `src/clipflow/ui/presenter.py` (держит, пока есть активная работа и включена настройка; отпускает при простое, выключении настройки и `shutdown`). Test: `tests/unit/test_keep_awake.py`, `tests/ui/test_presenter.py`.

- [ ] Step 1: тесты — `test_hold_and_release_on_mac` (подменённый `run`; `terminate` при `release`; повторный `hold` не плодит процессы); `test_hold_and_release_on_windows` (подменённый `kernel32`); `test_launch_failure_is_silent`; `test_presenter_holds_while_working`; `test_keep_awake_released_on_shutdown`.
- [ ] Step 2: запуск → FAIL. Step 3: реализация (ОС — через `sys.platform`, подменяемый в тестах). Step 4: `pytest tests/unit/test_keep_awake.py tests/ui/test_presenter.py -q` → passed.
- [ ] Step 5: commit `feat: keep the computer awake while downloading`.

### Task 6: Уведомление о завершении

**Files:** Modify `src/clipflow/ui/presenter.py` (сигнал `queue_finished = Signal(int, int)`: при переходе исполнителя к простою, если за заход есть COMPLETED/FAILED; отменённые и паузы ожидания не считаются), `src/clipflow/ui/window.py` (`notifier` — `QSystemTrayIcon` с иконкой приложения, показывается при первом уведомлении; `showMessage` при `notify_done`). Test: `tests/ui/test_notifications.py`.

- [ ] Step 1: тесты — `test_finished_run_notifies_once` («Скачано: 3, с ошибкой: 1»; подменённый `showMessage`); `test_only_cancelled_does_not_notify`; `test_rate_limit_pause_is_not_finished`; `test_notify_off_is_silent`; `test_texts_follow_language`.
- [ ] Step 2: запуск → FAIL. Step 3: реализация. Step 4: `pytest tests/ui/test_notifications.py tests/ui/test_presenter.py -q` → passed.
- [ ] Step 5: commit `feat: notify when downloads finish`.

### Task 7: Скрытие скачанного

**Files:** Modify `src/clipflow/ui/queue_model.py` (`QueueFilter.hide_completed: bool`, `show_hide_completed(bool)`; не действует в истории и на экране группы), `src/clipflow/ui/window.py` (флаг из настроек), `src/clipflow/ui/sidebar.py` (счётчики видимого). Test: `tests/ui/test_queue_filter.py`, `tests/ui/test_queue_search_window.py`.

- [ ] Step 1: тесты — `test_hide_completed_single_and_group`; `test_partly_failed_group_stays_visible`; `test_history_shows_everything`; `test_counts_follow_hidden`.
- [ ] Step 2: запуск → FAIL. Step 3: реализация. Step 4: `pytest tests/ui -q` → passed.
- [ ] Step 5: commit `feat: hide finished downloads from the lists`.

### Task 8: Документы и полная проверка

- [ ] Step 1: README, CHANGELOG («## Следующая версия»), `docs/PROJECT-MEMORY.md`.
- [ ] Step 2: `rm -rf .ruff_cache && .venv/bin/python scripts/check.py` → «All offline Qt checks and coverage gates passed.»
- [ ] Step 3: живой прогон: плейлист из 3 коротких роликов с `.m3u8` и субтитрами, скорость 1 МБ/с, повторная вставка того же плейлиста с «Пропускать» — треки не добавлены; снимок раздела «Дополнительные».
- [ ] Step 4: commit `docs: settings part 5a`.
