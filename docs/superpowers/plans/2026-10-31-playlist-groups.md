# Плейлист одной строкой — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Плейлист YouTube и профиль Instagram в общем списке — одна строка со сводкой; по «›» открывается экран группы с её треками/постами; над группой доступны групповые действия.

**Architecture:** Хранение не меняется. Сводка группы считается чистой функцией в `application/groups.py`; плоская `JobListModel` получает индекс потомков и кеш размеров; `QueueFilter` получает режим «верхний уровень / группа `<id>`»; `QueueDelegate` рисует строку группы; `QueuePanel` показывает полосу экрана группы. Групповые пауза/продолжение/повтор — пакетные методы `Scheduler` по одному снимку очереди.

**Tech Stack:** Python 3.12, PySide6 (Qt Widgets), pytest 9 / pytest-qt, ruff 0.17.3.

**Spec:** `docs/superpowers/specs/2026-10-31-playlist-groups-design.md`

## Global Constraints

- Формат очереди и настроек, `Job`, `DownloadRequest` не меняются; очередь 2.0.6 читается как есть.
- Действия и вид обычной строки, «Остановить всё», «Очистить всё», добавление ссылок и тексты ошибок не меняются.
- Новые тексты — ключи в `ui/i18n.py` на русском и английском; тексты сводки — как в спецификации: «<N> видео» / «<N> постов», «скачано <K>», «<E> с ошибкой», «скачано <K> из <N> · сейчас: <название> · <процент>%», «Не удалось получить список · <причина>», части через ` · `.
- Скорость: на 700 потомках построение списка, «Остановить всё», «Очистить всё», групповые пауза/продолжение/повтор читают очередь не более фиксированного числа раз (как `test_stop_all_reads_a_long_queue_once`, `test_clear_all_reads_the_queue_a_fixed_number_of_times`).
- Пороги покрытия: ядро ≥95% строк и ≥90% ветвей, runtime ≥90%; ruff 100 символов, одинарные кавычки; перед итоговой проверкой — `rm -rf .ruff_cache`.
- Работа в `dev`; агент коммитит сам, push и CI — в Task 8. Версия и сборки — только по отдельной команде владельца. Финальное ревью — opus, effort high.
- Python — `.venv/bin/python`; UI-тесты с `QT_QPA_PLATFORM=offscreen`; полная проверка — `.venv/bin/python scripts/check.py`.
- Коммиты оканчиваются строкой `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. Прогресс или завершение трека, пока виден общий список: строка группы должна перерисоваться со свежей сводкой (ведь меняется строка потомка, а не родителя) — тест в Task 3.
2. Активация строки группы (двойной щелчок/Enter) сейчас вызывает `toggle_job` и поставила бы на паузу или повтор родителя — должна открывать экран группы — тест в Task 6.
3. Правый щелчок по строке группы при выделении нескольких строк: показывается меню только этой группы, действия касаются всей группы с потомками, а не одного родителя — тест в Task 7.
4. «Очистить всё» или «Убрать из списка», пока открыт экран этой группы: экран возвращается к общему списку, а не показывает пустой список чужой группы — тест в Task 6.
5. Старая очередь, где родитель плейлиста завершён, а часть потомков уже убрана из списка: сводка считает только оставшихся, не падает — тест в Task 1.

---

### Task 1: Сводка группы без Qt

**Files:**
- Create: `src/clipflow/application/groups.py`
- Test: `tests/unit/test_groups.py`

**Interfaces:**
- Produces:
  - `is_group(job: Job, has_descendants: bool) -> bool` — `parent_id is None` и (`link.kind in {PLAYLIST, PROFILE}` или `has_descendants`).
  - `descendants(jobs: Iterable[Job]) -> dict[str, tuple[Job, ...]]` — для каждого задания верхнего уровня все задания, связанные с ним цепочкой `parent_id`, в порядке списка; один проход плюс разворот цепочек без повторного обхода списка; сироты (родитель отсутствует) не попадают ни в одну группу.
  - `top_level_id(job_id: str, jobs_by_id: Mapping[str, Job]) -> str | None` — корень цепочки `parent_id` (используется моделью для перерисовки строки группы).
  - `@dataclass(frozen=True) GroupSummary`: `total: int`, `completed: int`, `failed: int`, `active: int`, `size_bytes: int`, `current: Job | None`, `parent: Job`.
  - `group_summary(parent: Job, members: Sequence[Job], sizes: Mapping[str, int]) -> GroupSummary` — `failed` считает `FAILED` и `CANCELLED`; `active` — нетерминальные; `current` — первый потомок в `DOWNLOADING`/`PROCESSING`/`PROBING`; `size_bytes` — сумма `sizes.get(id, 0)` по `COMPLETED`.

- [ ] **Step 1: Write the failing tests** — `test_groups.py`, помощник `job(id, parent=None, state=..., kind=...)` по образцу `tests/unit/test_history.py`:
  - `test_playlist_without_children_is_a_group` — `is_group(playlist_parent, False) is True`; `is_group(single_video, False) is False`; `is_group(single_video, True) is True`; `is_group(child, True) is False`.
  - `test_descendants_follow_parent_chains` — родитель `p`, дети `c1`, `c2`, повтор `r` с `parent_id='c1'`, одиночное `s`: `descendants(...)['p'] == (c1, c2, r)` по идентификаторам, `descendants(...)['s'] == ()`.
  - `test_orphans_belong_to_no_group` (Review Focus 5) — потомок с `parent_id='gone'` не попадает ни в одну группу и не ломает подсчёт.
  - `test_summary_counts_states_and_sizes` — 3 `COMPLETED` (размеры 10, 20, отсутствует), 1 `FAILED`, 1 `CANCELLED`, 1 `QUEUED`, 1 `DOWNLOADING`: `total=7, completed=3, failed=2, active=2, size_bytes=30, current.id == <downloading>`.
  - `test_summary_of_an_empty_group` — `total == 0`, `current is None`, `parent` — переданный родитель.
  - `test_top_level_id_walks_to_the_root` — для `r` возвращает `'p'`, для отсутствующего родителя — `None`.

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/unit/test_groups.py -q` — Expected: ошибка импорта `clipflow.application.groups`.

- [ ] **Step 3: Implement** функции и `GroupSummary` в `src/clipflow/application/groups.py` (без Qt и без доступа к диску; слой `application` — тест слоёв `tests/unit/test_layers.py` должен остаться зелёным).

- [ ] **Step 4: Run** `.venv/bin/python -m pytest tests/unit/test_groups.py tests/unit/test_layers.py -q` — Expected: PASS.

- [ ] **Step 5: Commit** — `feat: summarize playlist and profile groups`.

### Task 2: Пакетные пауза, продолжение и повтор в Scheduler

**Files:**
- Modify: `src/clipflow/application/scheduler.py` (рядом с `pause`, `resume`, `retry`)
- Test: `tests/unit/test_scheduler.py`

**Interfaces:**
- Produces:
  - `Scheduler.pause_many(job_ids: Iterable[str]) -> tuple[str, ...]` — по одному снимку `repository.list()` ставит на пользовательскую паузу нетерминальные и не стоящие на паузе задания; останавливает активное, если оно среди них; возвращает изменённые id.
  - `Scheduler.resume_many(job_ids) -> tuple[str, ...]` — возобновляет `PAUSED` с `pause_reason == 'user'`, без `source_required`, без действующего `next_allowed_at`; один `_pump()` в конце.
  - `Scheduler.retry_many(job_ids) -> tuple[str, ...]` — переводит `FAILED`/`CANCELLED` без `source_required` в `QUEUED` (как `retry`); один `_pump()` в конце.
  - Неподходящие задания пропускаются молча (в отличие от одиночных методов, которые бросают `JobRuleError`).

- [ ] **Step 1: Write the failing tests** в `tests/unit/test_scheduler.py` (используя `CountingRepository`, `ControlledExecutor`, `request` этого файла):
  - `test_group_pause_reads_a_long_queue_once` — 700 `QUEUED` потомков, `pause_many(all_ids)`: все `PAUSED` с `pause_reason == 'user'`, `repo.reads <= 2`.
  - `test_group_resume_skips_jobs_that_cannot_resume` — `user`-пауза возобновляется; пауза `selection_required`, задание с `source_required` и с будущим `next_allowed_at` остаются как были; возвращаются только возобновлённые id.
  - `test_group_retry_requeues_failed_and_cancelled_only` — `FAILED` и `CANCELLED` → `QUEUED` с `error is None`; `COMPLETED` и `source_required` не тронуты; 700 потомков — `repo.reads <= 2`.
  - `test_group_pause_stops_the_active_job` — активное задание среди id получает `('<id>', 'pause')` в `worker.stops`.

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/unit/test_scheduler.py -q -k group` — Expected: FAIL, `AttributeError: 'Scheduler' object has no attribute 'pause_many'`.

- [ ] **Step 3: Implement** три метода по образцу `_cancel` (один снимок, сохранение по заданию, `_stop` и `_pump` по одному разу).

- [ ] **Step 4: Run** `.venv/bin/python -m pytest tests/unit/test_scheduler.py -q` — Expected: PASS.

- [ ] **Step 5: Commit** — `feat: pause, resume and retry many jobs from one queue snapshot`.

### Task 3: Индекс потомков, размеры и сводка в модели

**Files:**
- Modify: `src/clipflow/ui/queue_model.py` (`JobListModel`)
- Test: `tests/ui/test_queue_groups.py` (новый)

**Interfaces:**
- Consumes: `descendants`, `is_group`, `top_level_id`, `group_summary`, `GroupSummary` (Task 1).
- Produces:
  - `JobListModel.GroupRole` — следующая роль после `JobRole`; для строки группы — `GroupSummary`, для остальных — `None`.
  - `JobListModel.members(group_id: str) -> tuple[Job, ...]` — потомки группы из индекса.
  - `JobListModel.is_group_row(row: int) -> bool`.
  - Кеш размеров: `id → байты` для `COMPLETED` заданий с файлами; ключ инвалидируется при смене `result_files`; отсутствующий файл — 0. Диск читается только при первом запросе размера задания.
  - При `update_job` потомка дополнительно испускается `dataChanged` для строки его группы верхнего уровня.

- [ ] **Step 1: Write the failing tests** (`make_window`, задания добавляются в `window.presenter.repository` и `presenter._reload_jobs()`, как в `test_clear_all_reads_the_queue_a_fixed_number_of_times`):
  - `test_group_row_carries_its_summary` — плейлист-родитель и 3 потомка (один `COMPLETED` с реальным файлом 5 байт): `GroupRole` строки родителя — сводка `total=3, completed=1, size_bytes=5`; у потомков `GroupRole is None`.
  - `test_child_progress_repaints_the_group_row` (Review Focus 1) — подписка на `dataChanged`; `model.update_job(child, ProgressChanged(...))` испускает сигнал, диапазон которого включает строку родителя.
  - `test_file_sizes_are_read_once` — счётчик вызовов `Path.stat` (monkeypatch) не растёт при повторных запросах `GroupRole`.

- [ ] **Step 2: Run** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ui/test_queue_groups.py -q` — Expected: FAIL (`GroupRole` отсутствует).

- [ ] **Step 3: Implement** индекс в `set_jobs` (один вызов `descendants`), поддержку в `update_job`, кеш размеров и `GroupRole` в `data()`.

- [ ] **Step 4: Run** тот же файл и `tests/ui/test_queue_actions.py tests/ui/test_history_actions.py` — Expected: PASS.

- [ ] **Step 5: Commit** — `feat: group index, file sizes and summaries in the queue model`.

### Task 4: Фильтр верхнего уровня и экрана группы

**Files:**
- Modify: `src/clipflow/ui/queue_model.py` (`QueueFilter`)
- Test: `tests/ui/test_queue_groups.py`

**Interfaces:**
- Consumes: `JobListModel.members`, `is_group_row` (Task 3).
- Produces:
  - `QueueFilter.show_group(group_id: str | None)` — `None`: режим верхнего уровня (задания без `parent_id`); id: только потомки этой группы. По умолчанию — верхний уровень.
  - `QueueFilter.group_id: str | None`.
  - В режиме верхнего уровня группа проходит фильтр статуса и `history`, если ему отвечает хотя бы один потомок; группа без потомков — по состоянию родителя. Площадка — по площадке группы.

- [ ] **Step 1: Write the failing tests:**
  - `test_a_playlist_of_76_is_one_row` — родитель + 76 потомков + 1 одиночное: `proxy.rowCount() == 2`.
  - `test_group_screen_lists_only_its_members` — `show_group('p')`: 76 строк, все с `parent_id` из группы; `show_group(None)` — снова 2.
  - `test_status_tabs_follow_group_content` — 70 `COMPLETED`, 2 `FAILED`, 4 `QUEUED`: группа видна во вкладках `active`, `completed`, `failed`; на экране группы `failed` даёт 2 строки, `completed` — 70.
  - `test_group_without_members_filters_by_its_parent` — плейлист-родитель `FAILED` без потомков виден только во `failed` и `all`.

- [ ] **Step 2: Run** — Expected: FAIL (`show_group` отсутствует / 77 строк).

- [ ] **Step 3: Implement** режим в `filterAcceptsRow`; переключение через `beginFilterChange`/`endFilterChange`, как `show_status`.

- [ ] **Step 4: Run** `tests/ui/test_queue_groups.py` и весь `tests/ui` — Expected: PASS; существующие тесты, которые считают строки потомков в общем списке, при необходимости переводятся на экран группы с пояснением в коммите.

- [ ] **Step 5: Commit** — `feat: show groups as one row and filter by their content`.

### Task 5: Строка группы в QueueDelegate и тексты

**Files:**
- Modify: `src/clipflow/ui/queue_delegate.py`, `src/clipflow/ui/i18n.py`, `src/clipflow/ui/job_status.py` (функция текста сводки)
- Test: `tests/ui/test_queue_groups.py`, `tests/ui/test_texts.py` (существующая проверка ключей на обоих языках)

**Interfaces:**
- Consumes: `GroupSummary`, `GroupRole`.
- Produces:
  - `group_text(summary: GroupSummary, translator: Translator) -> str` в `job_status.py` — вторая строка сводки по правилам спецификации; размер в «КБ / МБ / ГБ» с одним знаком после запятой; для Instagram — «постов», для YouTube — «видео» (склонение — по образцу `_job_word`).
  - `QueueDelegate._group_buttons(rect) -> tuple[QRect, QRect, QRect]` — «папка», «⋮», «›» справа.
  - Новые значения `action_requested`: `'open_group'`, `'group_menu'`, `'group_folder'`.
  - Ключи i18n: `group_videos`, `group_posts`, `group_downloaded`, `group_progress`, `group_failed`, `group_list_failed`, `show_tracks`, `show_posts`, `group_menu.pause`, `group_menu.resume`, `group_menu.retry_failed`, `group_menu.open_folder`, `group_menu.remove`, `group_menu.delete_files`, `group_back`.

- [ ] **Step 1: Write the failing tests:**
  - `test_group_text_variants` — для сводок из Task 1: «76 видео · скачано 40 · 4,3 ГБ»; с ошибками и без активных — «76 видео · скачано 70 · 6 с ошибкой · …»; идёт загрузка — «скачано 40 из 76 · сейчас: <название> · 35%»; пустой упавший родитель — «Не удалось получить список · <error_text>»; профиль — «12 постов …».
  - `test_group_row_buttons_emit_actions` — клик в прямоугольники трёх кнопок строки группы даёт `('p', 'group_folder')`, `('p', 'group_menu')`, `('p', 'open_group')`; кнопки обычной строки не изменились.
  - Проверка, что все новые ключи есть на обоих языках, — существующим тестом ключей i18n.

- [ ] **Step 2: Run** — Expected: FAIL (`group_text` отсутствует).

- [ ] **Step 3: Implement** `group_text`, ветку отрисовки группы в `paint` (заголовок как сейчас, вторая строка — `group_text`, цвет `error`, если `failed > 0 and active == 0`), кнопки и `editorEvent`.

- [ ] **Step 4: Run** `tests/ui tests/unit -q` — Expected: PASS.

- [ ] **Step 5: Commit** — `feat: draw playlist and profile rows with a summary`.

### Task 6: Экран группы в QueuePanel

**Files:**
- Modify: `src/clipflow/ui/queue_panel.py`, `src/clipflow/ui/window.py` (`_row_action`)
- Test: `tests/ui/test_queue_groups.py`

**Interfaces:**
- Consumes: `QueueFilter.show_group`, `group_text`, действия делегата (Task 5).
- Produces:
  - `QueuePanel.open_group(group_id: str)`, `QueuePanel.close_group()`, `QueuePanel.group_id: str | None`.
  - `QueuePanel.group_bar` — виджет с `back_button`, `group_title`, `group_details`; виден только на экране группы.
  - `window._row_action`: `'open_group'` → `queue_panel.open_group`, `'group_folder'` → `presenter.open_group_folder` (Task 7), `'group_menu'` → меню группы (Task 7).
  - Активация (`activated`) строки группы открывает экран группы вместо `toggle_job`.
  - Счётчик и числа на вкладках статуса считают строки текущего режима.

- [ ] **Step 1: Write the failing tests:**
  - `test_open_and_back_restore_the_list` — прокрутка общего списка на строке N, «›» открывает экран (видна `group_bar`, 76 строк), `back_button.click()` возвращает 2 строки, вертикальная прокрутка и текущий индекс прежние.
  - `test_escape_returns_from_a_group` — `qtbot.keyClick(queue_view, Qt.Key_Escape)` на экране группы возвращает к общему списку.
  - `test_activating_a_group_row_opens_it` (Review Focus 2) — `view.activated.emit(index_группы)`: экран открыт, состояние родителя в репозитории не изменилось.
  - `test_screen_returns_when_its_group_disappears` (Review Focus 4) — открыт экран группы, `presenter.clear_all()`; после `qtbot.waitUntil` `panel.group_id is None`.
  - `test_counts_follow_the_screen` — в общем списке `count_label` говорит о 2 строках; на экране группы — о 76.

- [ ] **Step 2: Run** — Expected: FAIL (`open_group` отсутствует).

- [ ] **Step 3: Implement** полосу над списком, переключение, запоминание `verticalScrollBar().value()` и текущего индекса, Esc в `QueueView.keyPressEvent`, проверку исчезновения группы по `jobs_changed`.

- [ ] **Step 4: Run** `tests/ui -q` — Expected: PASS.

- [ ] **Step 5: Commit** — `feat: open a playlist or profile on its own screen`.

### Task 7: Действия над группой

**Files:**
- Modify: `src/clipflow/ui/presenter.py`, `src/clipflow/ui/presenter_clearing.py`, `src/clipflow/ui/window_dialogs.py` (`history_menu`, новое `group_menu`)
- Test: `tests/ui/test_queue_groups.py`

**Interfaces:**
- Consumes: `Scheduler.pause_many/resume_many/retry_many` (Task 2), `JobListModel.members` (Task 3), `deletion_paths`, `prune_empty_folders`.
- Produces:
  - `WorkbenchPresenter.pause_group(group_id)`, `resume_group(group_id)`, `retry_group_failures(group_id)`, `open_group_folder(group_id)`, `remove_group(group_id)`, `delete_group_files(group_id, confirmed=False)` — все через `_command`.
  - `open_group_folder`: общий родительский каталог `result_files` потомков (`os.path.commonpath`), если он внутри папки загрузки и существует; иначе `request.options.folder` группы; отсутствие — `error_raised('folder_missing')`.
  - `remove_group`: отменяет поддерево (`scheduler.cancel(group_id)`) и убирает группу с потомками той же отложенной очисткой, что `clear_all` (`ClearingController`, без удаления файлов).
  - `delete_group_files`: только при `confirmed=True`, при простаивающем исполнителе и терминальных потомках — `deletion_paths` + удаление + `prune_empty_folders`.
  - `WindowDialogs.group_menu(group_id, position)` — пункты по спецификации; «Приостановить все» доступно, если есть нетерминальные непаузные; «Продолжить все» — если есть `user`-паузы; «Повторить неудачные» — если есть `FAILED`/`CANCELLED` без `source_required`; «Удалить файлы с диска…» — с подтверждением, как `confirm_delete`.
  - `history_menu`: если строка под курсором — группа, показывает `group_menu` для неё одной.

- [ ] **Step 1: Write the failing tests:**
  - `test_group_pause_and_resume_cover_all_members` — 5 `QUEUED`: после `pause_group` все `PAUSED`; после `resume_group` все `QUEUED`.
  - `test_retry_failures_only_touches_failed_members` — 2 `FAILED`, 1 `COMPLETED`: `FAILED` → `QUEUED`, `COMPLETED` без изменений.
  - `test_group_folder_is_the_common_folder` — файлы в `downloads/YouTube/Плейлист [id]/` открывают этот каталог (monkeypatch `QDesktopServices.openUrl`).
  - `test_remove_group_takes_its_members_and_keeps_files` — после `remove_group` в репозитории нет ни родителя, ни потомков; файлы на месте.
  - `test_delete_group_files_needs_confirmation` — без подтверждения файлы на месте; с подтверждением файлы и опустевшая папка плейлиста удалены, записи остались.
  - `test_context_menu_on_a_group_acts_on_the_whole_group` (Review Focus 3) — выделены группа и одиночная строка, правый щелчок по группе: меню содержит пункты группы; «Убрать из списка» убирает группу с потомками и не трогает одиночную строку.
  - `test_group_actions_read_a_long_queue_a_fixed_number_of_times` — 700 потомков: `pause_group`, `resume_group`, `retry_group_failures` каждое читает очередь не более 4 раз (счётчик как в `test_clear_all_reads_the_queue_a_fixed_number_of_times`).

- [ ] **Step 2: Run** — Expected: FAIL (`pause_group` отсутствует).

- [ ] **Step 3: Implement** методы presenter, `ClearingController` для группы, `group_menu` и ветку в `history_menu`; подключить `'group_folder'` и `'group_menu'` в `window._row_action`.

- [ ] **Step 4: Run** `tests/ui tests/unit -q` — Expected: PASS.

- [ ] **Step 5: Commit** — `feat: pause, resume, retry, open, remove and delete a whole group`.

### Task 8: Документация, полная проверка, живой прогон, ревью, push

**Files:**
- Modify: `docs/CHANGELOG.md` (раздел «Следующая версия»), `README.md` (описание очереди), `docs/PROJECT-MEMORY.md`, `Agents/ClipFlow/memory/MEMORY.md`, память Claude `clipflow-project.md`.

- [ ] **Step 1:** Описать в CHANGELOG и README: плейлист и профиль — одна строка со сводкой, экран по «›», групповые действия, фильтры по содержимому.
- [ ] **Step 2:** `rm -rf .ruff_cache && .venv/bin/python scripts/check.py` — Expected: `All offline Qt checks and coverage gates passed.`, пороги ≥95/90/90.
- [ ] **Step 3:** Живой прогон на Mac из исходников в отдельном профиле (`CLIPFLOW_DATA_DIR` в scratchpad, короткая папка загрузки): плейлист YouTube на ~10 треков и профиль Instagram (последние 10): одна строка, сводка обновляется во время загрузки, экран группы, «←», «Приостановить все» / «Продолжить все», «Открыть папку». Записать результат.
- [ ] **Step 4:** Финальное ревью субагентом opus, effort high, по пакету `review-package` с планом, спецификацией и Review Focus; Critical/Important — одним проходом исправлений с тестом RED→GREEN.
- [ ] **Step 5:** Commit документации, `git push origin dev`, дождаться GitHub Checks на обеих ОС — Expected: Windows и macOS success.
