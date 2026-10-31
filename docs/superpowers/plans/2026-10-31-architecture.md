# Подпроект 3: архитектура — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Однонаправленные зависимости слоёв под тестом, крупные объекты разбиты по обязанностям, ruff `C901`/`BLE001` включены без временных исключений; поведение не меняется.

**Architecture:** Храповик: сначала правила включаются с пометками `# подпроект 3` на 43 местах, затем срезы снимают свои пометки. Публичные методы/сигналы `WorkbenchPresenter` и атрибуты `MainWindow`, которыми пользуются тесты, сохраняются делегированием. Новые чистые функции и классы — через TDD; переносы проверяются существующими тестами.

**Tech Stack:** Python 3.12, PySide6, pytest/pytest-qt, ruff 0.17.3, coverage-гейты `scripts/check_coverage.py`.

**Spec:** `docs/superpowers/specs/2026-10-31-architecture-design.md`

## Global Constraints

- Поведение программы и тексты интерфейса не меняются; единственное видимое отличие — подсказка строки ошибки показывает точный код правила вместо `action_failed`.
- Сборки Windows/Mac не делаются; версия не поднимается; работа прямо в `dev`.
- Тестовые ожидания не ослабляются; правка теста — только по существу (новое место импорта, публичная функция вместо приватного класса), с объяснением в коммите.
- Пороги: ядро (`/domain/`, `/application/`) ≥95% строк и ≥90% ветвей, всё ≥85% строк.
- ruff: длина строки 100, одинарные кавычки; `[tool.ruff.lint.mccabe] max-complexity = 10`.
- Временная пометка ровно `# подпроект 3`; итоговая пометка широкого `except` — `# noqa: BLE001  # <настоящая причина>`.
- Точки сборки, которым разрешены любые импорты: `clipflow.__main__`, `clipflow.ui.bootstrap`, `clipflow.ui.self_test`, `clipflow.infrastructure.auth_process.__main__`, `clipflow.infrastructure.auth_process.window`. Пакет `auth_process` не переносится.
- Python запускается как `.venv/bin/python`; полная проверка — `.venv/bin/python scripts/check.py`. Падение `test_batch_shortcut_ctrl_command_n` при заблокированном экране Mac (`ioreg -n Root -d1` → `CGSSessionScreenIsLocked=Yes`) — среда, не регрессия; тогда пороги считаются по прогону без него и это записывается в ledger.
- Коммиты оканчиваются строкой `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. Отмена во время загрузки после разборки `MediaPipeline.save`: `WorkCancelled` должен дойти до воркера как отмена, а не стать `download_failed`/`write_failed` — тест в Task 6.
2. Ошибка удаления файла при «Очистить всё» с удалением файлов: код `file_delete_failed` показан один раз, периодический тик не повторяет разрушительный ввод-вывод — тест в Task 8.
3. Выход из аккаунта ставит на паузу только активные задания этого профиля — тест в Task 9.
4. Смена состояния аккаунтов сбрасывает кеш проверки ссылки (иначе показываются качества, полученные без входа) — тест в Task 9.
5. Проброшенные атрибуты окна — те же объекты, что внутри частей (иначе тесты и сигналы держат «мёртвые» виджеты): `window.start_button is window.queue_panel.start_button` и т. п. — тест в Task 10.

---

### Task 0: Храповик правил

**Files:**
- Modify: `pyproject.toml` (`[tool.ruff.lint]`)
- Modify: 43 строки в `src/clipflow/**` (только комментарии)

**Interfaces:**
- Produces: пометки `# noqa: C901  # подпроект 3` и `# noqa: BLE001  # подпроект 3` на всех текущих нарушениях; последующие задачи снимают свои.

- [ ] **Step 1: Включить правила.** `select = ["E", "W", "F", "I", "B", "UP", "SIM", "C90", "BLE"]`, добавить секцию `[tool.ruff.lint.mccabe]` с `max-complexity = 10`.
- [ ] **Step 2: Убедиться, что храповик ловит.** Run: `.venv/bin/ruff check . --statistics` — Expected: `25 BLE001`, `18 C901`, exit 1.
- [ ] **Step 3: Поставить пометки.** `.venv/bin/ruff check . --add-noqa`, затем дописать ` # подпроект 3` к каждому добавленному `# noqa: …` (только этим 43 строкам). После `ruff format` пометка должна остаться на строке с нарушением (для `C901` — строка `def`, для `BLE001` — строка `except`).
- [ ] **Step 4: Проверить.** Run: `.venv/bin/ruff check . && .venv/bin/ruff format --check . && grep -rn "# подпроект 3" src | wc -l` — Expected: ruff чисто, `43`.
- [ ] **Step 5: Полная проверка и коммит.** Run: `.venv/bin/python scripts/check.py` — Expected: `All offline Qt checks and coverage gates passed.` Commit: `chore: enable complexity and blind-except rules with pending markers`.

### Task 1: Ошибки правил задания с кодами

**Files:**
- Create: `src/clipflow/application/errors.py`
- Modify: `src/clipflow/application/scheduler.py` (строки 80, 84, 162, 164, 166, 230, 232, 248, 250, 267, 269, 283), `src/clipflow/application/submission.py:63,130`, `src/clipflow/ui/presenter.py:71-84`
- Test: `tests/unit/test_scheduler.py`, `tests/unit/test_submission.py`, `tests/ui/test_workbench.py`

**Interfaces:**
- Produces: `class JobRuleError(ValueError)` с `__init__(self, code: str, message: str)` и атрибутом `code`; `RULE_CODES: frozenset[str]` — ровно `{'scheduler_closed', 'job_not_startable', 'source_required', 'job_not_resumable', 'cooldown_active', 'job_not_retryable', 'source_not_expected', 'source_changed', 'selection_not_expected', 'invalid_mode', 'job_not_repeatable'}`. `str(error)` — прежний английский текст сообщения.

- [ ] **Step 1: Тесты.**
  - В `test_scheduler.py` к каждому существующему `pytest.raises(ValueError)` добавить проверку кода: `with pytest.raises(JobRuleError) as raised: ...; assert raised.value.code == '<код>'` по таблице спецификации (сохранить и то, что это `ValueError`: `assert isinstance(raised.value, ValueError)` в одном параметризованном тесте).
  - В `test_submission.py:84` аналогично (`invalid_mode` или `job_not_repeatable` — по тому, что вызывает тест) и новый тест `test_repeat_of_active_job_raises_job_not_repeatable`.
  - `tests/unit/test_scheduler.py::test_rule_codes_without_own_text_keep_the_generic_message`:
    ```python
    from clipflow.ui.i18n import CATALOG
    shown = {code for code in RULE_CODES if 'error.' + code in CATALOG['ru']}
    assert shown == {'source_changed', 'cooldown_active'}
    ```
  - `tests/ui/test_workbench.py::test_command_errors_use_codes_not_message_text` — фасад с подменённым `scheduler.start`: `JobRuleError('cooldown_active', 'x')` → `error_raised` выдаёт `'cooldown_active'`; простой `ValueError('Cooldown has not expired')` → `'action_failed'`.
- [ ] **Step 2: RED.** Run: `.venv/bin/python -m pytest tests/unit/test_scheduler.py tests/unit/test_submission.py tests/ui/test_workbench.py -k "rule or code or raises or repeat" -q` — Expected: ImportError `JobRuleError`.
- [ ] **Step 3: Реализация.** `application/errors.py` с `JobRuleError` и `RULE_CODES`; заменить все перечисленные `raise ValueError('…')` на `raise JobRuleError('<код>', '…')` с тем же текстом; в `_command` убрать обе ветки разбора текста — остаётся `code = getattr(error, 'code', 'action_failed')`.
- [ ] **Step 4: GREEN.** Тот же запуск — Expected: PASS. Затем `.venv/bin/python scripts/check.py` — PASS.
- [ ] **Step 5: Commit.** `refactor: raise coded job rule errors instead of parsing messages`.

### Task 2: Группы сбоев в домене

**Files:**
- Create: `src/clipflow/domain/failures.py`
- Modify: `src/clipflow/ui/job_status.py` (убрать `_GROUPS`, `ERROR_GROUPS`, `AUTH_SETTINGS_CODES`)
- Test: `tests/unit/test_failures.py` (новый), `tests/ui/test_job_status.py` (импорт)

**Interfaces:**
- Produces: `FAILURE_GROUPS: dict[str, str]` (код → группа; содержимое — нынешний `ERROR_GROUPS` без изменений), `AUTH_SETTINGS_CODES: frozenset[str]` (без изменений), `failure_group(code: str | None) -> str` (неизвестный и `None` → `'internal'`).

- [ ] **Step 1: Тест** `tests/unit/test_failures.py`:
  ```python
  assert failure_group('instagram_rate_limited') == 'network'
  assert failure_group('auth_required') == 'signin'
  assert failure_group(None) == 'internal'
  assert failure_group('never_seen') == 'internal'
  assert set(FAILURE_GROUPS.values()) == {'signin', 'access', 'network', 'save', 'processing', 'tool', 'changed', 'empty', 'internal'}
  ```
  и `test_job_status_holds_only_texts`: `not hasattr(clipflow.ui.job_status, 'ERROR_GROUPS')`. В `test_job_status.py` импорт `ERROR_GROUPS`/`AUTH_SETTINGS_CODES` заменить на `FAILURE_GROUPS`/`AUTH_SETTINGS_CODES` из `clipflow.domain.failures`.
- [ ] **Step 2: RED.** Run: `.venv/bin/python -m pytest tests/unit/test_failures.py -q` — Expected: ModuleNotFoundError.
- [ ] **Step 3: Перенос.** Таблица групп и `AUTH_SETTINGS_CODES` — в `domain/failures.py`; `job_status._reason` вызывает `failure_group`.
- [ ] **Step 4: GREEN.** Run: `.venv/bin/python -m pytest tests/unit/test_failures.py tests/ui/test_job_status.py -q` — PASS; `scripts/check.py` — PASS.
- [ ] **Step 5: Commit.** `refactor: classify failure codes in the domain`.

### Task 3: Тест слоёв и устранение утечек

**Files:**
- Create: `tests/unit/test_layers.py`
- Modify: `src/clipflow/domain/models.py` (+`MediaItem`, +`BROWSERS`), `src/clipflow/providers/base.py` (реэкспорт `MediaItem`), `src/clipflow/domain/paths.py:14-15`, `src/clipflow/infrastructure/auth.py:30` (импорт `BROWSERS`), `src/clipflow/ui/accounts.py:18`

**Interfaces:**
- Produces: `clipflow.domain.models.MediaItem` (тот же dataclass), `clipflow.domain.models.BROWSERS` (тот же кортеж); `clipflow.providers.base.MediaItem` и `clipflow.infrastructure.auth.BROWSERS` остаются доступны (импорт из домена).

- [ ] **Step 1: Тест** `test_layers.py::test_layer_dependencies`. Обходит `src/clipflow/**/*.py`, имя модуля из пути (`__init__` → пакет), `ast.walk` по всем `Import`/`ImportFrom` (включая внутри функций и под `TYPE_CHECKING`), берёт цели `clipflow.*`; слой — второй компонент имени (`clipflow.domain.x` → `domain`; `clipflow.version` → `version`). Разрешено:
  ```python
  ALLOWED = {
      'domain': {'domain'},
      'application': {'domain', 'application'},
      'providers': {'domain', 'application', 'providers'},
      'infrastructure': {'domain', 'application', 'providers', 'infrastructure', 'version'},
      'ui': {'domain', 'application', 'ui', 'version'},
  }
  ENTRY_POINTS = {'clipflow.__main__', 'clipflow.ui.bootstrap', 'clipflow.ui.self_test',
                  'clipflow.infrastructure.auth_process.__main__',
                  'clipflow.infrastructure.auth_process.window'}
  ```
  Модули верхнего уровня (`clipflow.version`, `clipflow.__init__`) не проверяются. Тест собирает нарушения строками `'<модуль> -> <импорт>'` и делает `assert violations == []`.
- [ ] **Step 2: RED.** Run: `.venv/bin/python -m pytest tests/unit/test_layers.py -q` — Expected: FAIL ровно с `clipflow.domain.paths -> clipflow.providers.base` и `clipflow.ui.accounts -> clipflow.infrastructure.auth`. Другие нарушения — значит таблица или разбор неверны; исправить тест, а не код.
- [ ] **Step 3: Перенос.** `MediaItem` и `BROWSERS` — в `domain/models.py`; `providers/base.py`: `from clipflow.domain.models import MediaItem` (имя используется в `ProbeResult.items`, поэтому реэкспорт не нарушает F401 и пометка не нужна); `domain/paths.py` импортирует `MediaItem` из `domain.models` (без `TYPE_CHECKING`, если цикла нет); `auth.py` и `accounts.py` берут `BROWSERS` из домена.
- [ ] **Step 4: GREEN.** Run: `.venv/bin/python -m pytest tests/unit/test_layers.py -q` — PASS; `scripts/check.py` — PASS.
- [ ] **Step 5: Commit.** `refactor: keep domain and ui free of outer-layer imports`.

### Task 4: История в слое приложения

**Files:**
- Create: `src/clipflow/application/history.py` (перенос `src/clipflow/ui/history.py` + новая функция)
- Delete: `src/clipflow/ui/history.py`
- Modify: `src/clipflow/ui/presenter.py` (`_flush_clear`), `src/clipflow/ui/queue_delegate.py:8`
- Test: `tests/unit/test_history.py` (новый), `tests/ui/test_history_actions.py:76` (импорт)

**Interfaces:**
- Produces: `HistoryError`, `result_status(job) -> str`, `deletion_paths(jobs, all_jobs) -> tuple[Path, ...]` (без изменений) и `removable_targets(jobs: Iterable[Job], pending: set[str]) -> set[str]` — алгоритм из `_flush_clear`: повторять `targets -= {j.parent_id for j in jobs if j.id not in targets}`, пока множество меняется.

- [ ] **Step 1: Тесты** `test_history.py`:
  - `test_parent_of_a_kept_child_is_kept`: родитель `p` и ребёнок `c` (`parent_id='p'`), `pending={'p'}` → `set()`.
  - `test_grandparent_chain_is_kept_through_a_kept_child`: `g ← p ← c`, `pending={'g','p'}` → `set()`.
  - `test_whole_family_is_removable`: `pending={'g','p','c'}` → `{'g','p','c'}`.
  - `test_unrelated_targets_are_removable`: `pending={'x'}` при отсутствии детей → `{'x'}`.
  - Плюс прямые тесты `deletion_paths` на ветки, которые раньше покрывались только из UI, если гейт ветвей ядра это потребует (ядро теперь включает этот модуль).
- [ ] **Step 2: RED.** Run: `.venv/bin/python -m pytest tests/unit/test_history.py -q` — Expected: ModuleNotFoundError.
- [ ] **Step 3: Перенос и функция.** `git mv src/clipflow/ui/history.py src/clipflow/application/history.py` (отдельный коммит переноса без правок, затем функция — сохраняет blame); `_flush_clear` вызывает `removable_targets`; обновить импорты.
- [ ] **Step 4: GREEN.** Run: `.venv/bin/python -m pytest tests/unit/test_history.py tests/ui/test_history_actions.py -q` — PASS; `scripts/check.py` — PASS, ядро ≥95/90.
- [ ] **Step 5: Commit.** `refactor: move history rules to the application layer` (перенос) и `refactor: extract removable clear targets`.

### Task 5: План имени медиа

**Files:**
- Create: `src/clipflow/providers/media_plan.py`
- Modify: `src/clipflow/providers/media.py` (`save`, строки 56-73)
- Test: `tests/unit/test_media_plan.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True) class MediaPlan: target: Path; work: Path; tag: str | None; post: PostIdentity | None` и `plan_media(request: DownloadRequest, item: MediaItem) -> MediaPlan` (без ввода-вывода: `mkdir` и поиск готового файла остаются в `save`).

- [ ] **Step 1: Тесты** `test_media_plan.py`:
  - YouTube: `plan.tag == 'clipflow:' + media_identity(request, item)`, `plan.work == plan.target.with_name(plan.target.stem + '.' + media_identity(request, item))`, `plan.post is None`, `plan.target == output_path(request, item, item.info.get('author'), None)`.
  - Instagram с `post_code='ABC'`, `post_title='T'`, `published_at=datetime(2026,1,2)`: `plan.post == PostIdentity('ABC', 'T', datetime(2026,1,2))`, `plan.tag is None`, `plan.work == plan.target`.
  - Instagram без `post_code` и с `published_at='2026'` (строка): код — `request.link.canonical_id`, дата `None`.
  - GetCourse: `tag is None`, `post is None`.
- [ ] **Step 2: RED.** Run: `.venv/bin/python -m pytest tests/unit/test_media_plan.py -q` — ModuleNotFoundError.
- [ ] **Step 3: Реализация** и использование в `save`.
- [ ] **Step 4: GREEN.** Run: `.venv/bin/python -m pytest tests/unit/test_media_plan.py tests/integration/test_media_pipeline.py -q` — PASS.
- [ ] **Step 5: Commit.** `refactor: plan media names as a pure step`.

### Task 6: Модули MediaPipeline

**Files:**
- Create: `src/clipflow/providers/processes.py`, `src/clipflow/providers/conversion.py`, `src/clipflow/providers/publishing.py`
- Modify: `src/clipflow/providers/media.py`
- Test: `tests/integration/test_media_pipeline.py`

**Interfaces:**
- Consumes: `plan_media` (Task 5).
- Produces:
  - `processes.run_process(args, context, *, capture=False, capture_error=False, expected_retcodes=(0,))` и `processes.stop_process_tree(process, force=False)` — тела `_run`/`_stop_process_tree`.
  - `conversion.MediaTools(ffmpeg: str | None, ffprobe: str | None)` с `probe(path, context) -> dict`, `verify(path, item, request, context) -> None`, `convert(source, target, request, context, work=None, tag=None) -> Path` — тела `_probe`/`_verify`/`_convert`.
  - `publishing.numbered(target, n) -> Path`, `publishing.publish(temporary, target) -> Path`, `publishing.find_tagged(target, tag, context, probe) -> Path | None` (`probe` — `MediaTools.probe`), `publishing.write_caption(target, description, fmt) -> Path`.
  - `MediaPipeline` сохраняет: конструктор и атрибуты `ffmpeg`/`ffprobe`/`node`, `save`, `_run = staticmethod(run_process)`, `_telemetry` (остаётся в media.py), `_probe(self, path, context)` — делегирует в `MediaTools` (им пользуется `ui/self_test.py`). `save` — сценарий: план → готовый файл (`verify`) или `_download_photo`/`_download_video` → подпись → `FilesSaved`; блок `except` остаётся в `save`.

- [ ] **Step 1: Тест Review Focus 1** `test_cancel_during_download_is_reported_as_cancel_not_failure` в `test_media_pipeline.py`: подменить загрузку видео так, чтобы во время `process_ie_result` токен отмены был отменён и бросался `OSError` (как при обрыве записи); ожидание — `pytest.raises(WorkCancelled)`, не `MediaFailure`. Run — Expected: PASS уже сейчас (фиксирует поведение до разборки; если FAIL — это баг, разбирать через systematic-debugging до переноса).
- [ ] **Step 2: Переносы** — каждый модуль отдельным коммитом без смысловых правок. Тесты, подменяющие `media.os`/`media.subprocess`/`media.time`, подменяют общий модуль; если `media.py` больше не импортирует нужный модуль, тест переводится на модуль, где теперь код (`processes.subprocess`, `publishing.os`), с пояснением в коммите.
- [ ] **Step 3: Сценарий `save`** со снятием пометки `C901` у `save` (сложность ≤10). Пометку `BLE001` в `save` не трогать — Task 15.
- [ ] **Step 4: Проверка.** Run: `.venv/bin/ruff check src/clipflow/providers && .venv/bin/python -m pytest tests/integration/test_media_pipeline.py tests/integration/test_instagram_files.py tests/unit/test_transfer_telemetry.py tests/unit/test_youtube_provider.py tests/ui/test_package_self_test.py -q` — PASS; `scripts/check.py` — PASS.
- [ ] **Step 5: Commit(s).** `refactor: split process, conversion and publishing out of the media pipeline`, `refactor: make MediaPipeline.save a short scenario`.

### Task 7: Кеш проверки ссылки

**Files:**
- Create: `src/clipflow/application/probe_cache.py`
- Modify: `src/clipflow/ui/presenter.py` (`request_probe`, `clear_probe_cache`)
- Test: `tests/unit/test_probe_cache.py`

**Interfaces:**
- Produces: `class ProbeCache` с `__init__(self, *, ttl: float = 120.0, limit: int = 100, clock: Callable[[], float] = time.monotonic)`, `@staticmethod key_for(request: DownloadRequest) -> tuple` (те же 6 полей: `service`, `kind`, `canonical_id`, `auth_profile`, `media_filter`, `format == 'mp3'`), `get(key) -> tuple[int, ...] | None`, `put(key, heights: tuple[int, ...]) -> None`, `clear() -> None`.

- [ ] **Step 1: Тесты:** запись читается до 120 с и не читается на `clock()+120` (граница: `< ttl` — свежая); 101-я запись вытесняет самую старую; `clear()` опустошает; ключи двух запросов, отличающихся только `auth_profile`, различны; `mp3` и `mp4` различны, `mp4` и `webm` с одинаковым остальным — одинаковы.
- [ ] **Step 2: RED.** Run: `.venv/bin/python -m pytest tests/unit/test_probe_cache.py -q` — ModuleNotFoundError.
- [ ] **Step 3: Реализация** и замена `self._probe_cache` в презентере (`presenter._probe_cache` больше нет; тесты на него не ссылаются).
- [ ] **Step 4: GREEN.** Run: `.venv/bin/python -m pytest tests/unit/test_probe_cache.py tests/ui -q -k probe` — PASS; `scripts/check.py` — PASS.
- [ ] **Step 5: Commit.** `refactor: extract the probe cache`.

### Task 8: Очистка и удаление файлов

**Files:**
- Create: `src/clipflow/ui/presenter_clearing.py`
- Modify: `src/clipflow/ui/presenter.py`
- Test: `tests/ui/test_history_actions.py`

**Interfaces:**
- Consumes: `removable_targets`, `deletion_paths`, `HistoryError` (Task 4).
- Produces: `class ClearingController` с `__init__(self, presenter)` и методами `clear_all(delete_files: bool)`, `flush()`, `delete_files(job_ids)`, `remove_jobs(identities)`, `clear_history()`, `clear_queue()`; каждый — тело прежнего `action` (без `_command`). Фасад сохраняет одноимённые публичные методы: `return self._command(lambda: self._clearing.<метод>(...))`, а `_flush_clear` → `self._clearing.flush()`; `delete_files(job_ids, confirmed=False)` по-прежнему ничего не делает без `confirmed is True`.

- [ ] **Step 1: Тест Review Focus 2** `test_failed_file_delete_is_reported_once_and_not_retried_on_tick`: «Очистить всё» с удалением, `Path.unlink` подменён на `OSError` для одного файла; ожидание — один `error_raised('file_delete_failed')`, после двух вызовов `presenter._tick()` подменённый `unlink` больше не вызывался, задания остались в списке. Run — Expected: PASS до переноса (фиксирует поведение).
- [ ] **Step 2: Перенос** в `ClearingController`.
- [ ] **Step 3: Проверка.** Run: `.venv/bin/python -m pytest tests/ui/test_history_actions.py tests/ui/test_queue_actions.py tests/integration/test_shutdown_recovery.py -q` — PASS; `scripts/check.py` — PASS.
- [ ] **Step 4: Commit.** `refactor: move clearing out of the presenter`.

### Task 9: Аккаунты, названия, переключение задания

**Files:**
- Create: `src/clipflow/ui/presenter_accounts.py`, `src/clipflow/ui/presenter_titles.py`
- Modify: `src/clipflow/ui/presenter.py`
- Test: `tests/ui/test_accounts.py`, `tests/ui/test_queue_titles.py`, `tests/ui/test_workbench.py`

**Interfaces:**
- Produces:
  - `class AccountsController(QObject)` с `__init__(self, presenter)`; владеет `QTimer` опроса 1000 мс и снимком; методы `attach(gateway)`, `poll()`, `sign_in(service)`, `logout(service)`, `configure_getcourse(url, method, **values)`, `import_getcourse(url)`, `stop()`, свойство `gateway`. Фасад сохраняет `set_auth_gateway`, `_poll_auth`, `sign_in_account`, `logout_account`, `configure_getcourse`, `import_getcourse` и атрибут `auth_gateway` (свойство, читающее `self._accounts.gateway`).
  - `class TitleNamer(QObject)` с `__init__(self, presenter)`; одиночный `QTimer`, множество уже названных; методы `schedule()` (вызывается из `_tick`), `stop()`. Фасад сохраняет `title_interval_ms` (namer читает его у фасада при каждом запуске таймера — тесты меняют это значение у фасада).
  - `toggle_job`: словарь `JobState → метод` (`QUEUED` → старт, `PAUSED` → resume+старт, `FAILED`/`CANCELLED` → retry+старт, `COMPLETED` → `open_result`, иначе пауза); проверки `source_required` и `selection_required` — до словаря. Снять пометки `C901` у `toggle_job` и вложенного `action`.
- [ ] **Step 1: Тесты Review Focus 3 и 4** (должны пройти до переноса):
  - `test_logout_pauses_only_active_jobs_of_that_profile` (`test_accounts.py`): два активных задания с профилями `a` и `b`, выход из `a` → пауза только у задания `a`.
  - `test_auth_change_clears_probe_cache` (`test_workbench.py`): заполнить кеш, сменить статус шлюза, вызвать `presenter._poll_auth()` → следующий `request_probe` с тем же текстом идёт в исполнитель (кеш пуст).
- [ ] **Step 2: Перенос** аккаунтов, затем названий, затем `toggle_job` — три коммита.
- [ ] **Step 3: Проверка.** Run: `.venv/bin/ruff check src/clipflow/ui && .venv/bin/python -m pytest tests/ui tests/integration/test_shutdown_recovery.py -q` — PASS; `scripts/check.py` — PASS.
- [ ] **Step 4: Commits.** `refactor: move account polling out of the presenter`, `refactor: move background naming out of the presenter`, `refactor: dispatch job toggling by state`.

### Task 10: Боковая панель и панель очереди

**Files:**
- Create: `src/clipflow/ui/sidebar.py`, `src/clipflow/ui/queue_panel.py`
- Modify: `src/clipflow/ui/window.py` (`__init__`, `resizeEvent`, `_arrange_queue_controls`, `_filter_status`, `_update_counts`; `QueueView`, `NavigationButton` переезжают)
- Test: `tests/ui/test_workbench.py`

**Interfaces:**
- Produces:
  - `class Sidebar(QFrame)` в `sidebar.py` (`NavigationButton` — туда же) с `__init__(self, translator)`; атрибуты `nav_buttons`, `accounts_button`, `settings_button`; сигналы `navigate = Signal(object, bool, str)` (service или `None`, history, ключ) и `section = Signal(str)`; метод `set_compact(compact: bool)` (ширина 180/205).
  - `class QueuePanel(QWidget)` в `queue_panel.py` (`QueueView` — туда же) с `__init__(self, presenter, theme, translator)`; атрибуты `count_label`, `start_button`, `cancel_queue_button`, `clear_all_button`, `status_buttons`, `queue_view`, `proxy`, `empty`, `toolbar`, `status_tabs`; сигналы `clear_all_requested`, `row_action = Signal(str, str)`, `context_menu = Signal(QPoint)`; методы `arrange(available_width: int)` (прежняя логика переноса кнопок с состоянием `(wrapped, vertical)`), `update_counts(section: str, nav_buttons)`, `filter_status(status)`.
  - `MainWindow` пробрасывает (как обычные атрибуты, ссылки на те же объекты): `sidebar`, `nav_buttons`, `accounts_button`, `settings_button`, `queue_panel`, `queue_view`, `proxy`, `start_button`, `cancel_queue_button`, `clear_all_button`, `status_buttons`, `count_label`, `empty`, `queue_toolbar`, `status_tabs`.
- [ ] **Step 1: Тест Review Focus 5** `test_window_exposes_the_widgets_of_its_parts`: после создания окна `window.start_button is window.queue_panel.start_button`, `window.queue_view is window.queue_panel.queue_view`, `window.nav_buttons is window.sidebar.nav_buttons`, `window.accounts_button is window.sidebar.accounts_button`. Run — Expected: FAIL (`queue_panel` нет).
- [ ] **Step 2: Перенос** боковой панели, затем панели очереди (по коммиту).
- [ ] **Step 3: Проверка.** Run: `.venv/bin/python -m pytest tests/ui tests/integration/test_shutdown_recovery.py tests/platform -q` — PASS (включая перенос панели на ширине 880 px и высоту кнопок); `scripts/check.py` — PASS.
- [ ] **Step 4: Commits.** `refactor: extract the window sidebar`, `refactor: extract the queue panel`.

### Task 11: Меню и диалоги окна

**Files:**
- Create: `src/clipflow/ui/window_menus.py`, `src/clipflow/ui/window_dialogs.py`
- Modify: `src/clipflow/ui/window.py`
- Test: `tests/ui/test_queue_actions.py`, `tests/ui/test_submission_dialogs.py`, `tests/ui/test_history_actions.py`

**Interfaces:**
- Produces:
  - `build_menus(window) -> None` в `window_menus.py` — тело `_menus` (+ `_edit`, `_edit_enabled`, `_preferences` как функции модуля); выставляет `window.downloads_menu`, `window.language_actions`, `window.theme_actions` как раньше.
  - `class WindowDialogs` в `window_dialogs.py` с `__init__(self, window)`; методы `open_batch()`, `confirm_clear_all()`, `confirm_delete(identities)`, `history_menu(position)`, `select(identity, selection)`, `source(identity)`, `track(dialog)`; список открытых диалогов — `window._dialogs` (тот же объект).
  - `MainWindow` сохраняет методы `_open_batch`, `_confirm_clear_all`, `_confirm_delete`, `_history_menu`, `_select_dialog`, `_source_dialog`, `_track_dialog` как однострочные делегаты (тесты вызывают часть из них).
- [ ] **Step 1: Перенос** меню, затем диалогов — без смысловых правок.
- [ ] **Step 2: Проверка.** Run: `.venv/bin/python -m pytest tests/ui tests/platform -q` — PASS; `wc -l src/clipflow/ui/window.py` — меньше 450; `scripts/check.py` — PASS.
- [ ] **Step 3: Commits.** `refactor: build window menus in their own module`, `refactor: move window dialogs out of MainWindow`.

### Task 12: Тела воркеров исполнителя

**Files:**
- Create: `src/clipflow/infrastructure/work.py`
- Modify: `src/clipflow/infrastructure/executor.py` (`_ProbeWorker.run`, `_TitleWorker.run`, `_Worker.run`)
- Test: `tests/unit/test_executor_workers.py` (переход на публичные функции)

**Interfaces:**
- Produces:
  - `run_probe(request, provider, context) -> tuple[tuple[int, ...], str]` — (высоты по убыванию, код ошибки или `''`); коллекции, MP3 и «только фото» не опрашиваются.
  - `run_title(request, provider, context) -> str | None`.
  - `run_download(request, provider, context) -> WorkFinished | WorkStopped | WorkFailed`.
  - `class ProgressThrottle` с `__init__(self, interval: float = 0.5, clock=time.monotonic)` и `allow(payload) -> bool`; `check_provider_event(payload)` бросает `MediaFailure('invalid_provider_event')` на терминальных событиях.
  - Классы `QThread` создают `ExecutionContext` и вызывают эти функции; пометки `BLE001` переезжают вместе с `except` в `work.py` (снимаются в Task 15).
- [ ] **Step 1: Тесты.** Переписать `test_executor_workers.py` на функции `work.py` с теми же параметризациями и ожиданиями (`auth_required`, `probe_cancelled`, `rate_limit`, `probe_failed`, `(1080, 720)`, коллекции не опрашиваются, названия из пробелов → `None`, терминальные подтверждения, `invalid_provider_event`, троттлинг прогресса). Модульная строка документации: функции, а не приватные классы. Run — Expected: ImportError.
- [ ] **Step 2: Реализация** `work.py` и тонкие `run()`.
- [ ] **Step 3: Проверка.** Run: `.venv/bin/python -m pytest tests/unit/test_executor_workers.py tests/ui tests/integration -q` — PASS; `grep -n "_Worker\|_ProbeWorker\|_TitleWorker" tests` — пусто; `scripts/check.py` — PASS, запас runtime-покрытия не меньше, чем был (85,39%).
- [ ] **Step 4: Commit.** `refactor: run worker bodies as plain functions`.

### Task 13: Сложные функции ядра

**Files:**
- Modify: `src/clipflow/application/scheduler.py` (`handle`), `src/clipflow/application/submission.py` (`preview`), `src/clipflow/domain/paths.py` (`output_path`), `src/clipflow/domain/urls.py` (`parse_url`)
- Test: существующие `tests/unit/test_scheduler.py`, `test_submission.py`, `test_media_paths.py`, `test_urls.py`, `test_track_names.py`, `test_music.py`

**Interfaces:**
- Produces: `Scheduler.handle` — ранние выходы и словарь `type(payload) → self._on_<событие>` (`StageChanged`, `FilesSaved`, `RequestsDiscovered`, `TitleChanged`, `SelectionRequired`, `RateLimitDeferred`, подтверждения `_ACKS`); для `ProgressChanged` — только публикация; неизвестный тип — выход без публикации, как сейчас. Остальные функции — выделение именованных шагов (`parse_url` — разбор по хосту через функции `_youtube`, `_instagram`, `_getcourse`; `output_path` — выбор имени по сервису).
- [ ] **Step 1:** Для каждой функции перед правкой — Run соответствующего файла тестов, PASS. Если ветка функции не покрыта (`coverage report -m` по модулю), сначала добавить тест на неё (RED недоступен — это фиксация поведения, записать в ledger).
- [ ] **Step 2: Разбить** функцию, снять пометку `C901`.
- [ ] **Step 3: Проверка.** Run: `.venv/bin/ruff check src/clipflow/domain src/clipflow/application && .venv/bin/python -m pytest tests/unit -q` — PASS; `scripts/check.py` — PASS, ядро ≥95/90.
- [ ] **Step 4: Commit** по функции: `refactor: split <функция> into named steps`.

### Task 14: Остальные сложные функции

**Files:**
- Modify: `src/clipflow/infrastructure/auth.py` (`options_for`), `src/clipflow/infrastructure/auth_process/__main__.py` (`main`), `src/clipflow/infrastructure/settings.py` (`_migrate`), `src/clipflow/providers/access.py` (`run_pp`), `src/clipflow/providers/getcourse.py` (`_session`), `src/clipflow/providers/instagram_profile.py` (`execute`, `pages`), `src/clipflow/providers/youtube.py` (`probe`), `src/clipflow/ui/composer.py` (`__init__`), `src/clipflow/ui/queue_delegate.py` (`paint`), `src/clipflow/ui/self_test.py` (`main`)
- Test: существующие тесты этих модулей (`tests/platform/test_auth_compatibility.py`, `tests/unit/test_settings_migration.py`, `test_getcourse_provider.py`, `test_profile_discovery.py`, `test_youtube_provider.py`, `tests/ui/test_design_parity.py`, `test_package_self_test.py`, `test_themes.py`)

- [ ] **Step 1–4:** как в Task 13 для каждой функции: тесты модуля PASS до правки → разбиение на именованные шаги → снятие пометки `C901` → тесты PASS. `auth_process.main` и `self_test.main` — последовательность шагов-функций с ранним возвратом кода; `Composer.__init__` — методы построения частей (`_build_entry`, `_build_parameters`, …); `QueueDelegate.paint` — `_paint_background`, `_paint_text`, `_paint_actions`.
- [ ] **Step 5: Проверка.** Run: `.venv/bin/ruff check . && grep -rn "C901  # подпроект 3" src | wc -l` — `0`; `scripts/check.py` — PASS.
- [ ] **Step 6: Commit** по модулю: `refactor: split <функция> into named steps`.

### Task 15: Широкие except

**Files:**
- Modify: все места с `# noqa: BLE001  # подпроект 3` (25: `application/instagram_rate_policy.py`, `application/scheduler.py`, `infrastructure/auth.py` ×2, `auth_process/__main__.py`, `auth_process/window.py`, `infrastructure/work.py`/`executor.py` ×8, `infrastructure/platform.py`, `providers/getcourse.py`, `instagram_post.py`, `instagram_profile.py` ×2, `media.py`, `youtube.py`, `ui/presenter.py` ×2, `ui/self_test.py` ×2)
- Test: `tests/unit/test_layers.py::test_no_pending_markers`

**Interfaces:**
- Produces: у каждого места — либо узкий список исключений, либо `# noqa: BLE001  # <причина>` из набора: «граница потока: сбой становится кодом задания», «колбэк Qt: исключение в слоте не должно ронять цикл событий», «сторонняя библиотека: наружу только безопасный код, без секретов», «самопроверка сборки сообщает любой сбой», «команда интерфейса: любой сбой — код ошибки, окно живо».

- [ ] **Step 1: Тест** `test_no_pending_markers`: ни один файл `src/clipflow/**/*.py` не содержит `# подпроект 3`. Run — FAIL (25 мест).
- [ ] **Step 2: Разбор по месту.** Сужать только когда исключения, которые бросает вызываемый код, перечислимы и тест покрывает неожиданное исключение (оно не должно молча глотаться). Для каждого сужения — тест, что именно ожидаемое исключение превращается в код. Каждое решение — строка в ledger `Ruling: <файл:строка> — сужено до X / оставлено: <причина>`.
- [ ] **Step 3: GREEN.** Run: `.venv/bin/python -m pytest tests/unit/test_layers.py -q` — PASS; `.venv/bin/ruff check .` — чисто; `scripts/check.py` — PASS.
- [ ] **Step 4: Commit.** `refactor: justify or narrow every broad except`.

### Task 16: Документация, CI

**Files:**
- Modify: `docs/CHANGELOG.md` (раздел «Разработка — архитектура и границы слоёв»), `docs/PROJECT-MEMORY.md` (раздел подпроекта 3: коммиты, правила, отступления, отложенное), `docs/DEVELOPMENT.md` или `CONTRIBUTING.md` (таблица слоёв и где лежат части окна/презентера/конвейера), `AGENTS.md` (требование: не нарушать `test_layers.py`, сложность ≤10, `BLE001` только с причиной)

- [ ] **Step 1:** Обновить документы.
- [ ] **Step 2: Проверка.** Run: `.venv/bin/python scripts/check.py` — PASS.
- [ ] **Step 3: Commit и push.** `docs: record cleanup subproject 3`; `git push origin dev`.
- [ ] **Step 4: CI.** Дождаться GitHub Checks на точном SHA (`https://api.github.com/repos/kirillbronski/clipflow/commits/<sha>/check-runs`): Windows и macOS `success`. Падение Windows — разбирать (systematic-debugging, при необходимости Parallels), не перезапускать вслепую.
- [ ] **Step 5:** Финальное ревью всей ветки — субагент opus, effort high, пакет `review-package` от `ead7742`.
