# Подпроект 4: ревизия тестов — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Тесты проверяют поведение, не зависят от экрана/фокуса/скорости, не дублируют друг друга, общие фикстуры в `conftest.py`, покрытие честное и runtime ≥90%.

**Architecture:** Шесть тематических срезов по спецификации; каждый — свои коммиты и полный `scripts/check.py`. Фикстуры переезжают в `conftest.py`, помощники — в `tests/support/`; затем стабильность, отложенные проверки, правила ruff, покрытие, удаление лишнего. Push и CI — один раз в конце.

**Tech Stack:** Python 3.12, PySide6, pytest 9 / pytest-qt 4.5 / pytest-cov 7.1, coverage 7.17, ruff 0.17.3.

**Spec:** `docs/superpowers/specs/2026-10-31-test-revision-design.md`

Контекст до плана (31.10, по сообщению владельца): «Остановить всё»/«Очистить всё» на плейлисте ≈700 треков висели минутами. Исправлено вне плана: `b4cf2ea` (отмена очереди одним снимком, счётчики окна пересчитываются один раз на пачку событий; 700 заданий 305 с → 0,7 с; живой плейлист 710 треков — 0,58 с) и `e55cb23` (тест «Очистить всё» читает очередь фиксированное число раз). Эти тесты не трогаются, кроме переноса фикстур.

## Global Constraints

- Поведение программы не меняется, кроме текста `job_error.unknown` (Task 4).
- Тестовые ожидания не ослабляются; изменение ожиданий только там, где спецификация прямо меняет тест (Tasks 3–4), с объяснением в коммите.
- Пороги: ядро (`/domain/`, `/application/`) ≥95% строк и ≥90% ветвей; runtime ≥90% строк после Task 7 (до него — 85%).
- ruff: 100 символов, одинарные кавычки; перед итоговой проверкой каждой задачи — `rm -rf .ruff_cache`.
- Коммиты локальные; push и CI только в Task 9. Версия не поднимается, сборок нет; работа в `dev`.
- Python — `.venv/bin/python`; полная проверка — `.venv/bin/python scripts/check.py`.
- Коммиты оканчиваются строкой `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Число собранных тестов фиксируется до Task 1 (`pytest --collect-only -q | tail -1`); после переносов (Tasks 1, 5) оно не уменьшается, а после Task 8 уменьшается ровно на число удалённых тестов из ledger.

## Review Focus

1. Перенос фикстуры с именем, которое в модуле переопределено локальной функцией (`context`, `request`): тест должен использовать ту же реализацию, что раньше — проверяется равенством числа собранных и пройденных тестов до/после и прогоном каждого затронутого файла (Task 1).
2. `offscreen` по умолчанию в `check.py` не должен ломать прямой `pytest` и нативные шаги CI: при уже заданной `QT_QPA_PLATFORM` значение не трогается — тест в Task 2.
3. Замер дочерних процессов: `.coverage.*` объединяются, иначе порог считается по неполным данным или падает на Windows; после `check.py` в корне не остаётся `.coverage.*` — тест в Task 6.
4. `job_error.unknown` только для отсутствующего кода (`None`/`''`); неизвестный ненулевой код и битый код карусели по-прежнему дают `job_error.internal` — тест в Task 4.
5. Порог 90% должен выполняться на Windows, где ветки macOS не исполняются; если не выполняется — не снижать молча, а вынести владельцу (Task 9).

---

### Task 1: Фикстуры в conftest, помощники в tests/support

**Files:**
- Create: `tests/support/__init__.py`, `tests/support/workbench.py` (`HeldProvider`, `add`), `tests/support/media.py` (`item`, `request` медиа-теста, `probe`), `tests/support/scheduler.py` (`ControlledExecutor`, `request` планировщика), `tests/support/profiles.py` (`Source`, `codes`, `post`, `req`), `tests/support/auth.py` (`Process`, `seed`), `tests/support/youtube.py` (`extract_fixture`, `playlist`), `tests/support/rate.py` (`policy`), `tests/ui/conftest.py`, `tests/integration/conftest.py`
- Modify: `tests/conftest.py` (`make_window`, `batch`, `clipboard`), все `tests/**/test_*.py`, которые импортируют другой `test_*.py` (список: `grep -rn "from tests\.\(ui\|unit\|integration\|platform\)\.test_" tests`)
- Test: `tests/unit/test_layers.py::test_test_modules_do_not_import_each_other`

**Interfaces:**
- Produces: фикстуры `make_window`, `batch`, `clipboard` (корневой `tests/conftest.py`, так как ими пользуются `ui`, `integration`, `platform`); `media_server`, `tools`, `context` медиа-теста (`tests/integration/conftest.py`, если ими пользуются только `integration`; иначе корневой); обычные функции/классы — из `tests.support.<модуль>`. `tests.helpers`, `tests.instagram_fixtures`, `tests.fixtures` остаются.

- [ ] **Step 1: Зафиксировать базу.** Run: `.venv/bin/python -m pytest --collect-only -q -p no:cacheprovider | tail -1` — записать число в ledger.
- [ ] **Step 2: Тест** `test_test_modules_do_not_import_each_other`: обходит `tests/**/test_*.py`, `ast` все `Import`/`ImportFrom`; нарушение — цель вида `tests.<что угодно>.test_*`; `assert violations == []`. Run — Expected: FAIL со списком (≈40 импортов).
- [ ] **Step 3: Перенос.** Каждая фикстура (`@pytest.fixture`) — в `conftest.py`; каждая не-фикстура — в `tests/support/`. Если в модуле есть своя локальная функция с тем же именем, что у переносимой фикстуры, локальная остаётся (она переопределяет фикстуру только в своём модуле — как и сейчас). Импорты в тестах заменяются на `tests.support.*`; импорты фикстур удаляются (pytest находит их сам).
- [ ] **Step 4: Проверка.** Run: `.venv/bin/python -m pytest tests/unit/test_layers.py -q` — PASS; `--collect-only` — то же число, что в Step 1; `scripts/check.py` — PASS (кроме экранных тестов, см. Task 3).
- [ ] **Step 5: Commit.** `test: move shared fixtures to conftest and helpers to tests/support`.

### Task 2: Строгий ruff в тестах, offscreen и check.py

**Files:**
- Modify: `pyproject.toml` (`per-file-ignores` для `tests/**` — убрать `F401`, `F811`; `[tool.ruff] extend-include = ["packaging/*/*.spec"]`), `scripts/check.py`, `tests/integration/test_packaging_config.py`, `packaging/*/ClipFlow.spec`, `docs/TESTING.md`
- Test: `tests/integration/test_packaging_config.py`

**Interfaces:**
- Produces: `scripts/check.py`: `lint(run=subprocess.run) -> int`; `main(argv=None, *, run=subprocess.run)`; перед запуском тестов `os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')`.

- [ ] **Step 1: Тесты** в `test_packaging_config.py`: `offline_check` передаёт подставной `run` в `check.main(..., run=fake_run)` вместо `monkeypatch.setattr(check.subprocess, 'run', ...)`; новые `test_check_runs_qt_offscreen_by_default` (без переменной → после `main` в `os.environ['QT_QPA_PLATFORM'] == 'offscreen'`, `monkeypatch.delenv`) и `test_check_keeps_an_explicit_qt_platform` (`cocoa` остаётся `cocoa`). Run — Expected: FAIL (`main() got an unexpected keyword 'run'`).
- [ ] **Step 2: Реализация** в `scripts/check.py`.
- [ ] **Step 3: ruff.** Убрать игноры, включить `*.spec`; `.venv/bin/ruff check --fix .`, остальное вручную (неиспользуемые импорты в тестах удаляются; в `*.spec` глобалы PyInstaller (`Analysis`, `PYZ`, `EXE`, `COLLECT`, `BUNDLE`) — `# noqa: F821  # глобалы PyInstaller` или `per-file-ignores` для `packaging/**` = `["F821"]` с комментарием-причиной).
- [ ] **Step 4: Документация** `docs/TESTING.md`: локальный `check.py` идёт в `offscreen`; нативные проверки — те же команды, что в CI (`QT_QPA_PLATFORM=cocoa|windows CLIPFLOW_NATIVE_QA=1 …`, `CLIPFLOW_AUTH_NATIVE=1 …`).
- [ ] **Step 5: Проверка.** `rm -rf .ruff_cache`; `scripts/check.py` — PASS. Commit: `test: lint tests strictly and run the local check offscreen like CI`.

### Task 3: Стабильность

**Files:**
- Modify: `tests/platform/test_qt_clipboard.py`, `tests/platform/qt_dpi_probe.py`, `tests/ui/test_workbench.py`, `tests/ui/test_history_actions.py`, `tests/platform/test_auth_compatibility.py`, `tests/helpers.py`
- Test: те же файлы

**Interfaces:**
- Produces: `tests.helpers.wait_until(predicate, timeout=10.0, interval=0.025) -> None` (поднимает `AssertionError` по таймауту) — для ожиданий вне Qt.

- [ ] **Step 1: Command+N.** `test_batch_shortcut_ctrl_command_n` → `test_batch_action_has_new_shortcut_and_opens_dialog`: найти в `window.downloads_menu.actions()` действие с текстом `window.tr.text('batch')`; `QKeySequence(QKeySequence.StandardKey.New) in action.shortcuts()`; `action.trigger()` → `qtbot.waitUntil(lambda: bool(window._dialogs))`, `isinstance(window._dialogs[-1], BatchDialog)`. Прежнее нажатие клавиш — `test_native_new_shortcut_opens_batch_dialog` с `@pytest.mark.native_gui` и пропуском без `CLIPFLOW_NATIVE_QA=1`.
- [ ] **Step 2: DPI.** `test_separate_process_dpi` сравнивает с тем же экраном, на котором окно: база — `QGuiApplication.primaryScreen().devicePixelRatio()` вычисляется в самом `qt_dpi_probe.py` (без `CLIPFLOW_BASE_DPR` из родителя), а окно в пробе ставится на `primaryScreen()` (`window.setScreen(app.primaryScreen())` до `show()`), ожидание — `scale * base`. Проверить при подключённом внешнем мониторе (сбой 31.10: окно 2.0 при ожидании 1.0) и в `offscreen`.
- [ ] **Step 3: Таймер GUI** (`test_blocking_provider_does_not_block_gui_timer`): `qtbot.waitUntil(provider.started.is_set)`; `before = len(ticks)`; `qtbot.waitUntil(lambda: len(ticks) >= before + 5, timeout=5000)`; `assert not provider.torn_down.is_set()`; остальное как было.
- [ ] **Step 4: Перенос панели** (`test_bulk_toolbar_very_wide_buttons_stack_without_horizontal_scroll`): ждать `window.queue_panel.actions_layout.direction() == QBoxLayout.Direction.TopToBottom`, затем проверить порядок `y` всех трёх кнопок и отсутствие горизонтальной прокрутки.
- [ ] **Step 5: sleep.** Циклы `while … time.sleep(0.025)` в `test_auth_compatibility.py` → `wait_until(...)`. `sleep` внутри подставных провайдеров/процессов (`test_workbench.py:333`, `test_queue_titles.py:25`, `time.sleep(600)` дочернего процесса) остаются — они моделируют работу.
- [ ] **Step 6: Проверка.** Каждый изменённый тест — мутация: временно сломать проверяемое поведение (снять сочетание у действия; заблокировать GUI-поток в провайдере через прямой вызов; оставить панель горизонтальной) → тест падает; вернуть. `scripts/check.py` — PASS; дополнительно `QT_QPA_PLATFORM=cocoa CLIPFLOW_NATIVE_QA=1 .venv/bin/python -m pytest tests/platform/test_qt_clipboard.py -q` — PASS при разблокированном экране. Commit(s): `test: make focus, DPI, timing and layout tests independent of the machine`.

### Task 4: Отложенные проверки и текст при отсутствующем коде

**Files:**
- Modify: `src/clipflow/ui/job_status.py`, `src/clipflow/ui/i18n.py`, `src/clipflow/providers/media.py`, `src/clipflow/providers/instagram_profile.py`, `tests/ui/test_job_status.py`, `tests/ui/test_queue_actions.py`, `tests/ui/test_texts.py`, `tests/ui/test_queue_titles.py`
- Test: те же тестовые файлы

**Interfaces:**
- Produces: ключ каталога `job_error.unknown` = RU `'Загрузка не удалась. Повторите.'`, EN `'Download failed. Try again.'`.

- [ ] **Step 1: Тесты (RED).**
  - `test_missing_code_has_its_own_text`: `error_text(None, Service.INSTAGRAM, ru) == 'Загрузка не удалась. Повторите.'`, то же для `''`, EN `'Download failed. Try again.'`; `error_tooltip(None, Service.YOUTUBE, ru) == 'Загрузка не удалась. Повторите.'` (без строки «Код:»).
  - Параметризация `test_unknown_missing_or_malformed_codes_fall_back_to_internal` теряет `None` и `''` (переходят в новый тест), остальные коды по-прежнему → `INTERNAL_RU`; `test_tooltip_appends_code` — последняя проверка `None` переносится в новый тест.
  - `test_group_texts_ru_en` получает столбец `service`; строка `getcourse_auth_failed` — `Service.GETCOURSE` и тексты «Нужен вход в GetCourse. Откройте «Аккаунты».» / «Sign-in to GetCourse is required. Open Accounts.»; остальные строки — `Service.YOUTUBE`.
  - `test_icons_follow_theme`: цвет центрального непрозрачного пикселя глифа у `start_button` и `add_button` меняется при смене темы и совпадает с токеном темы (`t['text']` для `start_button`, `t['accent_text']` для `add_button`) с допуском 8 на канал.
  - `test_every_referenced_key_exists` и `test_removed_keys_are_gone_and_unreferenced` дополнительно ищут ключи-литералы в кортежах/списках, идущих в `tr.text`/`tr.bind`: шаблон `\(\s*'([a-z_][\w.]*)'\s*,` внутри `src/clipflow/ui/*.py`, отфильтрованный по `CATALOG` (ловит `('cancel_queue', ...)` из меню); тест проверяет, что найден хотя бы `cancel_queue`.
  Run: `.venv/bin/python -m pytest tests/ui/test_job_status.py tests/ui/test_queue_actions.py tests/ui/test_texts.py -q` — Expected: FAIL (`KeyError: 'job_error.unknown'` / текст internal).
- [ ] **Step 2: Реализация.** `job_status._reason`: `if not code: return translator.text('job_error.unknown')`; ключ в `CATALOG` (оба языка); `error_tooltip` уже возвращает только текст для пустого кода.
- [ ] **Step 3: Мелочи.** `test_queue_titles.py`: `zip(provider.calls, provider.calls[1:], strict=False)` → `itertools.pairwise(provider.calls)`; причины `# noqa: BLE001` у `MediaPipeline.save` и `InstagramProfileProvider.execute` → `# noqa: BLE001  # сторонняя библиотека и собственный конвейер: наружу только безопасный код`.
- [ ] **Step 4: Проверка.** Те же файлы — PASS; `test_texts` (каталоги RU/EN равны, семейство `job_error.` полное) — PASS; `scripts/check.py` — PASS. Commit: `fix: say "download failed" when a job failed without a code` и `test: check icon colour, tuple keys and the GetCourse sign-in text`.

### Task 5: Правила PT и RUF

**Files:**
- Modify: `pyproject.toml` (`select` += `"PT"`, `"RUF005"`, `"RUF012"`, `"RUF059"`, `"RUF100"`), `tests/**`, при необходимости `src/**`
- Test: весь набор

- [ ] **Step 1: Включить и посчитать.** `rm -rf .ruff_cache; .venv/bin/ruff check . --statistics` — записать числа в ledger (ожидаемо ≈189 PT018, 16 PT011, 11 PT006, 38 RUF059, 3 RUF012, 3 RUF100, 1 RUF005).
- [ ] **Step 2: Безопасные автоисправления** (`ruff check --fix .`: PT006, RUF100, RUF005 и др. safe) — отдельный коммит `test: apply safe pytest-style fixes`.
- [ ] **Step 3: Вручную по файлам.** PT018: `assert a and b` → отдельные `assert` в том же порядке; PT011: `match=` с устойчивой частью сообщения или точный тип (`JobRuleError`, `MediaFailure`, `HistoryError`, `InvalidLink`); RUF059: `_`-имена; RUF012: `ClassVar` или `__init__`. Смысл проверок не меняется. Коммиты по каталогам: `test: split compound assertions in tests/unit` и т. д.
- [ ] **Step 4: Проверка.** `--collect-only` — то же число; `scripts/check.py` — PASS. 

### Task 6: Замер дочерних процессов

**Files:**
- Modify: `pyproject.toml` (`[tool.coverage.run]` += `parallel = true`, `patch = ["subprocess"]`; убрать дубль заголовка `[tool.coverage.run]`), `scripts/check_coverage.py`, `.gitignore` (`.coverage.*`)
- Test: `tests/integration/test_packaging_config.py::test_coverage_combines_child_process_data`

**Interfaces:**
- Produces: `check_coverage.run()` после pytest вызывает `Coverage(config_file=...)` → `combine()` → `save()` → отчёт; файлы `.coverage.*` удаляются объединением.

- [ ] **Step 1: Тест** `test_coverage_combines_child_process_data`: во временной копии пустого проекта с двумя файлами данных (`.coverage.a`, `.coverage.b`, созданными `coverage.CoverageData` для разных строк одного модуля) функция объединения из `check_coverage` (`combine_data(root: Path) -> None`) даёт один `.coverage` со строками обоих и не оставляет `.coverage.*`. Run — Expected: FAIL (`combine_data` нет).
- [ ] **Step 2: Реализация** `combine_data` и вызов в `run()`.
- [ ] **Step 3: Проверка.** `scripts/check.py` — PASS; в отчёте `ui/self_test.py` и `infrastructure/auth_process/__main__.py` больше не 0%; в корне нет `.coverage.*`. Записать новые цифры в ledger. Commit: `test: measure code run in child processes`.

### Task 7: Покрытие до 90%

**Files:**
- Modify/Test: тесты модулей из спецификации: `tests/unit/test_platform.py` (новый, для `infrastructure/platform.py`), `tests/platform/test_auth_compatibility.py` (`auth.py`, `auth_process/sessions.py`), `tests/unit/test_executor_workers.py` и `tests/ui/test_workbench.py` (`executor.py`), `tests/ui/test_accounts.py` (`presenter.py`, `presenter_accounts.py`), `tests/unit/test_instagram_rate_policy.py`, `tests/integration/test_media_pipeline.py` (`processes.py`, `publishing.py`, `conversion.py`), `tests/ui/test_workbench.py` (`bootstrap.py`), `tests/integration/test_instagram_transport.py`, `tests/ui/test_history_actions.py` (`window_dialogs.py`)
- Modify: `scripts/check_coverage.py` (`'runtime_lines': (..., 0.90)`), `tests/integration/test_packaging_config.py` (ожидаемый порог, если он там зафиксирован)

- [ ] **Step 1: Список пропусков.** `coverage report -m` по модулям из списка — в ledger: модуль, непокрытые строки, какое поведение они реализуют.
- [ ] **Step 2: Тесты поведения**, модуль за модулем, в порядке пропусков. Имя теста — поведение («ключ шифрования создаётся один раз и переиспользуется», «сбой Keychain даёт auth_protection_failed без текста ключа», «закрытие исполнителя ждёт рабочий поток» и т. п.). Каждый новый тест проходит мутационную проверку: временно сломать проверяемую строку → тест падает. Платформенный код другой ОС: подмена (`monkeypatch` `os.name`, `keyring`, `ctypes` DPAPI) где честно возможно; иначе `# pragma: no cover  # только Windows` / `# только macOS` — каждая такая пометка в ledger с причиной.
- [ ] **Step 3: Порог.** Поднять `runtime_lines` до `0.90`. Run: `scripts/check.py` — PASS с запасом ≥0,5% на Mac; запас для Windows оценивается по числу строк с пометками «только Windows/macOS» и проверяется в CI (Task 9).
- [ ] **Step 4: Commits** по модулям: `test: cover <поведение> in <модуль>`; последний — `test: raise the runtime coverage gate to 90%`.

### Task 8: Лишние тесты

**Files:**
- Modify: тесты, признанные дублирующими

- [ ] **Step 1: Кандидаты.** Пройти по каталогам; кандидат — тест, чьи проверки целиком входят в проверки другого теста на том же входе, или тест внутренней детали, рядом с которым есть тест поведения. Список с парой «кандидат → замена» — в ledger.
- [ ] **Step 2: Доказательство.** Для каждой пары: удалить кандидата; временно сломать поведение, которое он проверял; тест-замена падает → удаление подтверждено; иначе кандидат остаётся (ledger: «оставлен, замена не ловит X»).
- [ ] **Step 3: Проверка.** `--collect-only` — число = база − удалённые; `scripts/check.py` — PASS, пороги выполнены. Commit: `test: remove tests duplicated by <замены>` (в теле — список пар).

### Task 9: Документация, CI, ревью

**Files:**
- Modify: `docs/TESTING.md`, `docs/CHANGELOG.md` (раздел «Разработка — ревизия тестов», плюс исправление отмены длинной очереди и текст `job_error.unknown`), `docs/PROJECT-MEMORY.md` (подпроект 4 и итог всей чистки), `AGENTS.md` (фикстуры только в `conftest.py`, помощники в `tests/support/`, тестовые модули не импортируют друг друга, PT/RUF), `tests/README.md`

- [ ] **Step 1: Документы** и `rm -rf .ruff_cache`; `scripts/check.py` — PASS.
- [ ] **Step 2: Финальное ревью** всей ветки от `9c0762b` — субагент opus, effort high (Review Focus этого плана, ledger `Ruling:`); исправления Critical/Important одним проходом RED→GREEN.
- [ ] **Step 3: Push** `git push origin dev`; GitHub Checks на точном SHA: Windows и macOS `success` (включая нативные шаги). Порог 90% на Windows не выполнен → не снижать, а отчитаться владельцу с цифрами.
- [ ] **Step 4:** `Agents/ClipFlow` (SYNC-MANIFEST, снимок, START-HERE, memory) и память Claude. Commit документации `docs: record cleanup subproject 4` и push (только документация).
