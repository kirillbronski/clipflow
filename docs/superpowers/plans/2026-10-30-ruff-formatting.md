# Единый стиль кода (ruff) — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** весь Python-код ClipFlow отформатирован ruff, проходит выбранные правила линтера, стиль закреплён в `scripts/check.py` (и через него в CI); поведение не меняется.

**Architecture:** конфигурация в `pyproject.toml`; один механический коммит `ruff format`; затем безопасные автоисправления; затем ручные правки маленькими коммитами; в конце — проверка стиля в `check.py` и документация.

**Tech Stack:** Python 3.12, ruff 0.17.3, pytest/pytest-qt, GitHub Actions (Windows + macOS).

**Spec:** `docs/superpowers/specs/2026-10-30-ruff-formatting-design.md`

## Global Constraints

- `line-length = 100`, `target-version = "py312"`, `quote-style = "single"`.
- `select = ["E", "W", "F", "I", "B", "UP", "SIM"]`; `"tests/**" = ["F811"]`; `C901`, `BLE001`, `N`, `PL`, `RUF`, `PT`, `S` не включать.
- ruff закреплён как `ruff==0.17.3` в `[project.optional-dependencies].dev`.
- Поведение не меняется: версия не поднимается, сборки не выпускаются; тестовые ожидания не ослабляются.
- Каждое `# noqa` указывает код правила и причину в том же комментарии.
- Коммиты в `dev`, push в `origin/dev`; `main` не трогать. Концовка сообщений коммитов — по системному напоминанию об авторстве.
- Проверка: `CLIPFLOW_DATA_DIR=<временная папка> PATH=/opt/homebrew/bin:$PATH .venv/bin/python scripts/check.py` → `All offline Qt checks and coverage gates passed.` (пороги: ядро ≥95% строк/≥90% ветвей, всё ≥85%).

## Review Focus

1. Перенос длинных строк в `ui/i18n.py` и `ui/themes.py` меняет текст или цвет → Task 4 сравнивает снимок `CATALOG` и `PALETTES` до/после.
2. Форматирование незаметно меняет смысл кода (склейка строк, скобки) → Task 2 сравнивает `ast.dump` каждого файла до/после.
3. На Windows CI `ruff` не находится как команда → Task 5 вызывает его как `sys.executable -m ruff`, проверка на CI обеих ОС.
4. Отложенные правки на Windows ПК владельца теряются при pull после форматирования → Task 2 начинается с напоминания владельцу и ожидания ответа.
5. `# noqa` без причины прячет реальную проблему → Task 4 проверяет, что каждый `noqa` содержит пояснение.

---

### Task 1: Конфигурация ruff

**Files:**
- Modify: `pyproject.toml` (секции `[project.optional-dependencies]`, новые `[tool.ruff]`, `[tool.ruff.format]`, `[tool.ruff.lint]`, `[tool.ruff.lint.per-file-ignores]`, `[tool.ruff.lint.flake8-bugbear]`)

**Interfaces:**
- Produces: `.venv/bin/ruff` версии 0.17.3; конфигурация, которую читают `ruff format` и `ruff check` без флагов.

- [ ] **Step 1:** добавить `ruff==0.17.3` в `dev`; добавить секции ruff со значениями из Global Constraints и `[tool.ruff.lint.flake8-bugbear] extend-immutable-calls = ["PySide6.QtCore.QModelIndex"]` (идиома Qt `parent=QModelIndex()` в `ui/queue_model.py`, `ui/batch_dialog.py`).
- [ ] **Step 2:** `.venv/bin/python -m pip install -r requirements-dev.txt`; `.venv/bin/ruff --version` → `ruff 0.17.3`.
- [ ] **Step 3:** `.venv/bin/ruff format --check . | tail -1` сообщает о файлах к форматированию (ожидаемо до Task 2); `git diff --stat` — только `pyproject.toml`.
- [ ] **Step 4:** коммит `build: configure ruff formatter and linter`.

### Task 2: Механическое форматирование

**Files:** все `*.py` в `src/`, `tests/`, `scripts/`, `run.py` (только `ruff format`).

**Interfaces:**
- Consumes: конфигурация Task 1.
- Produces: хеш коммита форматирования (нужен Task 3).

- [ ] **Step 1:** напомнить владельцу: на основном Windows ПК (`C:/Users/Kirill/PycharmProjects/ClipFlow`) закоммитить или отказаться от незакоммиченных правок и именованного stash, затем подтвердить. Ждать ответа владельца.
- [ ] **Step 2:** снять снимок `ast.dump(ast.parse(text))` для каждого `*.py` (скрипт во временной папке сессии, не в репозитории) в JSON.
- [ ] **Step 3:** `.venv/bin/ruff format .`; затем `ruff format --check .` → код выхода 0.
- [ ] **Step 4:** сравнить новый снимок AST с Step 2 → все файлы совпадают. Любое отличие — остановиться и разобрать.
- [ ] **Step 5:** полный `scripts/check.py` → PASS и пороги покрытия.
- [ ] **Step 6:** коммит `style: format the codebase with ruff` (только результат `ruff format`, без ручных правок).

### Task 3: Безопасные автоисправления и blame-ignore

**Files:**
- Create: `.git-blame-ignore-revs` (хеш Task 2 с комментарием-строкой о его смысле)
- Modify: файлы, затронутые `ruff check --fix` (импорты `I001`/`F401`, `UP017`, `UP012`, `E401` и другие safe fix)

**Interfaces:**
- Consumes: хеш коммита Task 2.

- [ ] **Step 1:** создать `.git-blame-ignore-revs` с полным хешем Task 2.
- [ ] **Step 2:** `.venv/bin/ruff check --fix .` (только safe fixes, без `--unsafe-fixes`); затем `ruff format .` (сортировка импортов может потребовать переформатирования).
- [ ] **Step 3:** просмотреть `git diff`: изменения только в импортах и выражениях, указанных в правилах. Удалённый «неиспользуемый» импорт, нужный ради побочного эффекта или реэкспорта (например, в `__init__.py`), вернуть с `# noqa: F401 — <причина>`.
- [ ] **Step 4:** полный `scripts/check.py` → PASS.
- [ ] **Step 5:** коммит `style: apply safe ruff fixes and ignore formatting in blame`.

### Task 4: Ручные правки оставшихся замечаний

**Files (по пробному прогону на копии; номера строк уточнить по `ruff check` после Task 3):**
- Modify: `ui/themes.py` (12× E501), `ui/i18n.py` (11× E501), `infrastructure/rate_limit_store.py`, `infrastructure/auth_process/window.py`, `ui/window.py`, `domain/paths.py`, `ui/queue_delegate.py`, `providers/media.py`, `infrastructure/executor.py`, `infrastructure/auth_process/__main__.py`, `scripts/*.py`, тесты с E501.
- Modify: `providers/instagram_profile.py` (E741 `l` → `line`), `ui/bootstrap.py` (F841 `theme`), `scripts/check.py` (F841 `args`), `scripts/build.py` (E402), `scripts/migrate_windows_data.py` (SIM102, B904), `infrastructure/auth.py`, `providers/media.py`, `ui/presenter.py` (SIM105 → `contextlib.suppress`), `providers/media.py` (SIM112 `SystemRoot`).
- Modify (тесты): `tests/integration/test_shutdown_recovery.py` (F841, SIM117), `tests/integration/test_instagram_transport.py` (SIM105, SIM117), `tests/integration/test_packaging_config.py` и `tests/ui/test_workbench.py` (B023), `tests/ui/test_queue_titles.py` и `tests/ui/test_themes.py` (B905).

- [ ] **Step 1:** снять снимок `CATALOG` (`clipflow.ui.i18n`) и `PALETTES` (`clipflow.ui.themes`) в JSON во временной папке.
- [ ] **Step 2:** E501: переносить строки неявной склейкой литералов в скобках или переносом аргументов; текст литералов не менять.
- [ ] **Step 3:** снимок `CATALOG`/`PALETTES` идентичен Step 1.
- [ ] **Step 4:** правила-без-изменения-поведения: E741 переименование; F841: если присваивание держит Qt-объект живым (как `theme` в `ui/bootstrap.py`), переименовать в `_theme` с комментарием о времени жизни; иначе удалить имя, сохранив вызов с побочным эффектом; SIM105 → `contextlib.suppress(...)`; SIM102/SIM117 — объединение; B904 → `raise ... from None` (как в остальном коде: не раскрывать причину); B905 → `zip(..., strict=True)` где длины обязаны совпадать (в `test_queue_titles` попарный `zip(calls, calls[1:])` — `strict=False`).
- [ ] **Step 5:** SIM112 в `providers/media.py`: имя переменной окружения для дочернего процесса Windows — `# noqa: SIM112 — точное имя Windows, передаётся в env подпроцесса` (поведение не меняем).
- [ ] **Step 6:** B023 в тестах: лямбда вызывается в той же итерации цикла (`qtbot.waitUntil` и аналоги) — привязать переменную аргументом по умолчанию (`lambda w=window: w.presenter.is_closed`); проверить, что тест по-прежнему ждёт тот же объект.
- [ ] **Step 7:** `.venv/bin/ruff check .` → `All checks passed!`; `ruff format --check .` → без изменений; `grep -rn "noqa" src tests scripts` — у каждого есть код и причина.
- [ ] **Step 8:** полный `scripts/check.py` → PASS.
- [ ] **Step 9:** коммиты по смыслу (минимум два): `style: wrap long lines without changing texts or colours`, `refactor: resolve remaining lint findings`.

### Task 5: Закрепление стиля и документация

**Files:**
- Modify: `scripts/check.py` (функция `lint() -> int` перед `run()`)
- Modify: `CONTRIBUTING.md`, `docs/DEVELOPMENT.md`, `AGENTS.md`, `docs/PROJECT-MEMORY.md`, `docs/CHANGELOG.md` (раздел «Текущие изменения»: только разработческое примечание)
- Test: `tests/integration/test_packaging_config.py` или новый `tests/unit/test_check_script.py`

**Interfaces:**
- Produces: `scripts/check.py: lint() -> int` — возвращает 0, если `[sys.executable, '-m', 'ruff', 'format', '--check', '.']` и `[sys.executable, '-m', 'ruff', 'check', '.']` (cwd=ROOT) оба вернули 0; иначе ненулевой код первого упавшего. `main()` вызывает `lint()` до `run()` и возвращает его код при ошибке.

- [ ] **Step 1: тест (RED)** `test_check_runs_lint_before_tests`: подменить `subprocess.run` так, чтобы вызов `ruff format --check` вернул код 1; `check.main([])` возвращает 1 и не вызывает `check_coverage.run`.
- [ ] **Step 2:** запустить тест → FAIL (lint ещё не вызывается).
- [ ] **Step 3:** реализовать `lint()` и вызов в `main()`; вывод ruff не перехватывать (виден в логе CI).
- [ ] **Step 4:** тест → PASS; полный `scripts/check.py` → PASS (ruff проходит, затем тесты и пороги).
- [ ] **Step 5:** документация: как запускать `ruff format .`/`ruff check --fix .`; `git config blame.ignoreRevsFile .git-blame-ignore-revs`; в `AGENTS.md` — код должен проходить `scripts/check.py` включая ruff; в `PROJECT-MEMORY.md` — итог подпроекта 1 с хешами коммитов.
- [ ] **Step 6:** коммит `build: enforce ruff in the offline check` и коммит документации; `git push origin dev`.
- [ ] **Step 7:** дождаться GitHub Checks на точном SHA: `Python 3.12 · windows-latest` и `Python 3.12 · macos-15` → success. При падении — разобрать по аннотациям (`/repos/kirillbronski/clipflow/check-runs/<id>/annotations`), исправить, повторить.
- [ ] **Step 8:** синхронизировать `Agents/ClipFlow` (копии по `SYNC-MANIFEST.json`, спецификация и план, snapshot, `START-HERE.md`, `memory/MEMORY.md`) и память Claude; остановиться и доложить владельцу перед подпроектом 2.
