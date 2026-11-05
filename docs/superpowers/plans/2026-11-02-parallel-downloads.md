# Одновременные загрузки, часть 5б — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** YouTube качает до N роликов сразу (N = 1–4 из настроек), рядом — по одной загрузке Instagram и GetCourse; лимит скорости — общий на все загрузки.

**Architecture:** Общий потокобезопасный `RateLimiter` в исполнителе, к которому каждая загрузка обращается из крючка прогресса yt-dlp (вместо `ratelimit`). Исполнитель запускает загрузки без требования «свободен». Планировщик ведёт словарь активных попыток и «полосы» по площадке с лимитами мест; ползунок в «Соединении» меняет лимит полосы YouTube.

**Tech Stack:** Python 3.12, PySide6, yt-dlp, pytest + pytest-qt, ruff 0.17.3.

**Spec:** `docs/superpowers/specs/2026-11-02-parallel-downloads-design.md`

## Global Constraints

- `AppSettings.youtube_parallel: int = 1`, допустимо 1–4 (целое, не `bool`); файл без поля → 1; неверное → настройки по умолчанию.
- Полосы: `Service.YOUTUBE` — `youtube_parallel` мест, `Service.INSTAGRAM` — 1, `Service.GETCOURSE` — 1.
- Тексты ru / en: строка «Одновременные загрузки YouTube» / «Simultaneous YouTube downloads»; пояснение «Сколько роликов YouTube качать сразу» / «How many YouTube videos to download at once»; подписи 1–4 «Безопасно / Обычно / Быстро / Рискованно» и «Safe / Normal / Fast / Risky»; предупреждение (при 3–4) «YouTube может временно заблокировать загрузки с вашего IP» / «YouTube may temporarily block downloads from your IP».
- Лимит: ведро токенов ёмкостью в одну секунду лимита; ожидание кусками по 0,1 с с проверкой отмены; смена лимита действует на идущие загрузки; `ratelimit` yt-dlp не передаётся; при лимите `concurrent_fragment_downloads=1` остаётся.
- Проверка качества и загрузки взаимоисключающи, как сейчас; `executor.is_idle` = «ни загрузок, ни проверки».
- Слои: `RateLimiter` — `infrastructure`; в `providers/base.py` только протокол `Limiter` и ничего не делающая реализация по умолчанию.
- Покрытие: ядро ≥95 % строк / ≥90 % ветвлений, программа ≥90 %.

## Review Focus

1. Позднее подтверждение остановки одной из трёх активных — освобождается только её место, остальные продолжают и их события принимаются — тест `test_late_ack_frees_only_its_slot` (Task 4).
2. Закрытие программы при трёх активных — все три на паузе `shutdown`, `executor.stop` вызван для каждой, новые не стартуют после подтверждений — тест `test_shutdown_pauses_every_active` (Task 4).
3. Синхронный исполнитель, завершающий задание прямо в `start`, при N=3 — без рекурсии, все задания очереди выполнены по порядку — тест `test_immediate_executor_with_parallel_slots` (Task 4).
4. Лимит Instagram (`RateLimitDeferred`) при идущих роликах YouTube — Instagram ждёт, YouTube продолжает и добирает новые — тест `test_instagram_deferral_leaves_youtube_running` (Task 4).
5. Лимит сняли («Без ограничений»), пока поток спит в `consume` — поток просыпается не позже чем через 0,2 с — тест `test_removing_limit_wakes_sleeper` (Task 1).

---

### Task 1: Общий лимит скорости

**Files:** Create `src/clipflow/infrastructure/rate_limiter.py`. Test: `tests/unit/test_rate_limiter.py`.

**Interfaces:** Produces `RateLimiter(clock=time.monotonic, sleep=time.sleep)` с методами `set_rate(bytes_per_second: int | None) -> None`, `consume(count: int, cancel: CancellationToken) -> None` (бросает `WorkCancelled` через `cancel.raise_if_cancelled()`), свойство `rate -> int | None`.

- [ ] Step 1: тесты с поддельными часами (сон двигает часы) — `test_no_limit_never_sleeps`; `test_total_of_two_threads_matches_rate` (два «потока» поочерёдно потребляют по 64 КБ при лимите 1 МиБ/с; за 5 с модельного времени потреблено ≤ 6 МиБ и ≥ 4 МиБ); `test_rate_change_applies_at_once` (лимит 1 МиБ/с → 10 МиБ/с: следующая порция 1 МиБ ждёт ≤ 0,2 с); `test_cancel_interrupts_wait` (`WorkCancelled`, сон вызван не более одного раза после отмены); `test_removing_limit_wakes_sleeper` (настоящий поток спит в `consume`, `set_rate(None)` из другого — `consume` возвращается за ≤ 0,2 с).
- [ ] Step 2: `pytest tests/unit/test_rate_limiter.py -v` — FAIL (нет модуля).
- [ ] Step 3: реализовать: `threading.Lock`; токены пополняются по `clock()` до ёмкости = `rate`; `consume` вычитает `count` (уходя в минус), затем, пока токены < 0 и лимит есть, спит `min(0.1, долг / rate)` и проверяет отмену; `set_rate` пересчитывает токены (новый лимит не даёт накопленного долга больше секунды).
- [ ] Step 4: тесты — PASS.
- [ ] Step 5: commit `feat: shared download rate limiter`.

### Task 2: Лимит в загрузках вместо `ratelimit`

**Files:** Modify `src/clipflow/providers/base.py` (`Limiter`, `ExecutionContext.limiter`), `src/clipflow/providers/media.py` (`_options`, `_telemetry`), `src/clipflow/infrastructure/executor.py` (`ThreadExecutor.preferences` как свойство, `_Worker` получает лимитер). Test: `tests/unit/test_media_options.py`, `tests/unit/test_executor_workers.py`.

**Interfaces:** Consumes `RateLimiter` (Task 1). Produces `class Limiter(Protocol): def consume(self, count: int, cancel: CancellationToken) -> None`; `NO_LIMIT` (ничего не делает); `ExecutionContext(..., limiter: Limiter = NO_LIMIT)`; `ThreadExecutor.limiter: RateLimiter`; присваивание `executor.preferences = DownloadPreferences(...)` вызывает `limiter.set_rate(preferences.rate_limit)`.

- [ ] Step 1: тесты — в `test_media_options.py`: `test_rate_limit_option` переписать в `test_rate_limit_is_not_a_ytdlp_option` (`'ratelimit' not in options(rate_limit=2 MiB)`), `concurrent_fragment_downloads` при лимите по-прежнему 1; `test_hook_reports_downloaded_bytes_to_limiter` (крючок `_telemetry` с записывающим лимитером получает `downloaded_bytes` 100, 250, 250, 400 → `consume` вызван с 100, 150, 150; повтор того же числа ничего не добавляет; уменьшение счётчика — новый файл/фрагмент — считается от нуля). В `test_executor_workers.py`: `test_preferences_set_limiter_rate` и `test_workers_share_one_limiter` (контекст двух запущенных загрузок содержит тот же объект `executor.limiter`).
- [ ] Step 2: запустить оба файла — FAIL.
- [ ] Step 3: реализовать; прирост считать по ключу `(data.get('filename'), data.get('fragment_index'))` от прошлого значения этого ключа.
- [ ] Step 4: оба файла и `tests/unit/test_media*.py` — PASS.
- [ ] Step 5: commit `feat: one rate limit across downloads`.

### Task 3: Исполнитель с несколькими загрузками

**Files:** Modify `src/clipflow/infrastructure/executor.py`. Test: `tests/unit/test_executor_workers.py`.

**Interfaces:** Produces `ThreadExecutor.start` отказывает (`ValueError('Executor unavailable')`) только при `_closing` или пока идёт проверка (`probing`); свойство `probing -> bool` (`_probe is not None or _pending_probe is not None`); `available` излучается после окончания любой загрузки, если не `_closing`.

- [ ] Step 1: тесты — `test_two_downloads_run_together` (два задания стартуют, оба события доходят, `is_idle` ложно до окончания обоих); `test_available_after_each_finish` (после окончания первой из двух — `available` 1 раз); `test_start_refused_while_probing`; `test_probe_waits_for_all_downloads` (проверка, запрошенная при двух загрузках, стартует после окончания второй).
- [ ] Step 2: FAIL.
- [ ] Step 3: реализовать.
- [ ] Step 4: `pytest tests/unit/test_executor_workers.py tests/ui -q -k "executor or probe or quality"` — PASS.
- [ ] Step 5: commit `feat: executor runs several downloads`.

### Task 4: Планировщик с полосами

**Files:** Modify `src/clipflow/application/scheduler.py`; `tests/support/scheduler.py` (`request(name, service=...)` для Instagram/GetCourse по ссылкам `https://www.instagram.com/p/<name>/` и уроку GetCourse из существующих фикстур). Test: `tests/unit/test_scheduler_parallel.py` (новый), `tests/unit/test_scheduler.py` (существующие должны остаться зелёными; правки только там, где тест опирался на «Instagram ждёт YouTube» — каждая правка с `Ruling:`).

**Interfaces:** Consumes `executor.probing` (через `getattr(..., 'probing', False)`). Produces `Scheduler.limits: dict[Service, int]` (все по 1), `Scheduler.set_youtube_parallel(count: int) -> None` (`ValueError` вне 1–4; затем `_pump`), `Scheduler.active_ids -> tuple[str, ...]`; внутренняя `_Attempt(attempt_id, launched=False, discovered=False, stopping=False)`; `_active: dict[str, _Attempt]`.

- [ ] Step 1: тесты в `test_scheduler_parallel.py` (ControlledExecutor; `worker.emit(payload, run=i)`): `test_lanes_fill_in_queue_order` (N=3, очередь «YT1 YT2 IG1 YT3 YT4 GC1 IG2» → стартуют YT1 YT2 IG1 YT3 GC1); `test_finished_youtube_starts_next_youtube` (окончание YT2 → YT4); `test_second_instagram_waits_for_first`; `test_lowering_limit_keeps_running_jobs` (N=3 → 1: никто не остановлен, окончание двух YT ничего не запускает, окончание третьего — запускает YT4); `test_raising_limit_starts_more_at_once`; `test_preferred_job_waits_only_in_its_lane` (`start('YT4')` при занятой полосе: IG1 стартует, YT4 — первым при освобождении); `test_late_ack_frees_only_its_slot`; `test_pause_cancel_and_clear_queue_stop_each_active` (`stops` содержит все три, места заняты до `WorkStopped` каждой); `test_shutdown_pauses_every_active`; `test_old_attempt_events_are_dropped`; `test_probing_blocks_new_starts`; `test_immediate_executor_with_parallel_slots`; `test_instagram_deferral_leaves_youtube_running`; `test_set_youtube_parallel_rejects_out_of_range` (0, 5).
- [ ] Step 2: `pytest tests/unit/test_scheduler_parallel.py -v` — FAIL.
- [ ] Step 3: реализовать: `_pump` в цикле выбирает первое ожидающее задание, у полосы которого `active < limit` (сначала `_preferred_job`, если его полоса свободна; иначе он остаётся предпочтительным), запускает, повторяет; выход — нет подходящих, `probing`, `not _running`, `_closed`. Все места с `self._active == (...)`, `_launched`, `_discovered`, `_stopping` переходят на запись `_active[job_id]`; `_drained` ставится, только когда ожидающих нет вовсе (как сейчас).
- [ ] Step 4: `pytest tests/unit/test_scheduler_parallel.py tests/unit/test_scheduler.py tests/integration -q` — PASS.
- [ ] Step 5: commit `feat: scheduler runs youtube in parallel lanes`.

### Task 5: Ползунок в настройках

**Files:** Modify `src/clipflow/infrastructure/settings.py`, `src/clipflow/ui/settings_page.py` (`_build_connection`), `src/clipflow/ui/i18n.py`, `src/clipflow/ui/presenter.py` (`_apply_runtime_settings`). Test: `tests/unit/test_settings_migration.py`, `tests/ui/test_settings_page.py`, `tests/ui/test_presenter.py`.

**Interfaces:** Consumes `Scheduler.set_youtube_parallel` (Task 4). Produces `SettingsPage.parallel_slider` (`QSlider`, 1–4, `TicksBelow`, шаг 1), `parallel_label` (подпись значения), `parallel_warning` (`QLabel`, objectName `error` — имеющийся цвет предупреждений темы, видим при 3–4); сохранение через `presenter.update_preferences(youtube_parallel=n)`.

- [ ] Step 1: тесты — `test_youtube_parallel_round_trip` (по умолчанию 1; 3 сохраняется; `0`, `5`, `True`, `'2'` → настройки по умолчанию; файл без поля → 1); `test_parallel_slider_labels_and_warning` (значения 1–4 → подписи из Global Constraints; предупреждение скрыто на 1–2, видно на 3–4; английский язык — английские тексты); `test_parallel_slider_saves` (сдвиг на 2 → `presenter.settings.youtube_parallel == 2` и `scheduler.limits[Service.YOUTUBE] == 2`); `test_parallel_applied_at_startup` (презентер с настройкой 4 → лимит полосы 4).
- [ ] Step 2: FAIL.
- [ ] Step 3: реализовать (сохранение по `valueChanged`; строка — под пояснением к «Скорости»).
- [ ] Step 4: три файла — PASS; `pytest tests/ui -q` — PASS.
- [ ] Step 5: commit `feat: simultaneous youtube downloads setting`.

### Task 6: Документы, полная проверка, живой прогон

**Files:** Modify `README.md` (раздел настроек), `docs/CHANGELOG.md` («## Следующая версия»), `docs/PROJECT-MEMORY.md` (раздел «5б»: решения, рулинги).

- [ ] Step 1: документы.
- [ ] Step 2: `.venv/bin/python scripts/check.py > <workspace>/check.log 2>&1` — зелёный, пороги покрытия выполнены.
- [ ] Step 3: живой прогон на Mac (`.venv/bin/python -m clipflow`): N=3, плейлист YouTube из 4 роликов + пост Instagram — в работе сразу три ролика и пост; лимит 2 МБ/с — сумма скоростей строк ≈ 2 МБ/с; закрытие во время загрузок — при следующем запуске продолжаются.
- [ ] Step 4: commit `docs: parallel downloads (5b)`.
