# Проверки

Python 3.12, `pip install -r requirements-dev.txt`; `python scripts/check.py` запускает весь новый pytest suite и coverage gates. `--qt` остаётся совместимым alias, старого UI больше нет. `tests/legacy-parity.json` описывает замену всех 11 прежних scripts; production функции не извлекаются через AST.

`scripts/check.py` запускает тесты в `QT_QPA_PLATFORM=offscreen`, если переменная не задана, — как основной шаг CI: заблокированный экран, фокус или масштаб монитора не влияют на результат. Нативные проверки запускаются отдельно (ниже) с явной платформой.

Unit tests проверяют контракты/ошибки и scheduler; integration — настоящий localhost HTTP, resume, FFmpeg/FFprobe и SQLite; UI — настоящие Qt Widgets; platform — clipboard, protected auth и process lifecycle. Все используют временный CLIPFLOW_DATA_DIR. Поддельные upstream ответы обозначены fixtures; это не live проверки.

```powershell
$env:QT_QPA_PLATFORM='windows'
$env:CLIPFLOW_NATIVE_QA='1'
$env:CLIPFLOW_AUTH_NATIVE='1'
python -m pytest tests/platform tests/ui tests/integration/test_shutdown_recovery.py -q
```

На Mac — то же с `QT_QPA_PLATFORM=cocoa` (экран не заблокирован, окно может получить фокус); затем выполнить [T16a](MAC-T16A.md). Offscreen не заменяет native clipboard/DPI. Windows symlink test может явно пропускаться без системной привилегии; причины всех skips должны присутствовать в отчёте.

`scripts/check_coverage.py --reuse` принимает отчёт только для того же runtime fingerprint. В знаменателе все собственные src файлы, включая child-only модули; нет исключений ради процента. Пороги: ядро (`domain`, `application`) — 95% строк и 90% ветвей, весь runtime — 90% строк. CI проверяет Windows и macOS на точном commit.

Замер включает дочерние процессы, запущенные тестами (окно входа, самопроверка сборки): `[tool.coverage.run]` — `parallel = true`, `patch = ["subprocess"]`. Файлы `.coverage.*` объединяет pytest-cov в конце прогона; `check_coverage.combine_data` перед отчётом подбирает оставшиеся (если дочерний процесс завершился позже). Окно входа WebEngine (`auth_process/window.py`) исполняется только в нативном шаге и остаётся непокрытым. Тела `QThread.run` coverage не видит (поток запускает Qt), поэтому их логика вынесена в `infrastructure/work.py` и проверяется напрямую. Код, который может исполниться только на другой ОС и не проверяется подменой, помечается `# pragma: only windows` или `# pragma: only macos`: он исключается из замера только на другой ОС (`CLIPFLOW_FOREIGN_OS` выставляет `check_coverage.py`). Обычный `# pragma: no cover` не используется.

## Как устроены тесты

- Общие фикстуры — только в `conftest.py` того уровня, где ими пользуются (`tests/conftest.py`, `tests/integration/conftest.py`); помощники-не-фикстуры — в `tests/support/` и `tests/helpers.py`. Тестовый модуль не импортирует другой `test_*.py` (проверяет `tests/unit/test_layers.py`).
- ruff для тестов действует целиком, включая `F401`/`F811`, `PT` (`pytest.raises` с `match=` или точным типом, имена `parametrize` кортежем, без составных `assert a and b`) и `RUF005`/`RUF012`/`RUF059`/`RUF100`.
- Тест называет поведение, а не строку кода. Новый тест для уже существующего поведения проверяется мутацией: проверяемая строка временно ломается — тест должен упасть. Тест удаляется, только если мутацию ловит другой тест.
- Ожидание — по условию (`qtbot.waitUntil`, `tests.helpers.wait_until`, `Event.wait`), не `time.sleep` с жёстким сроком.
- На macOS тесты шифруют сессии настоящим Keychain под сервисом `ClipFlow Tests` (ключ программы — `ClipFlow`, его тесты не трогают). В конце прогона `tests/conftest.py` удаляет эти ключи (`tests/support/keychain.py`); ключи, созданные самопроверкой собранной программы, Python удалить не может — их убирают вручную в «Связке ключей» поиском «ClipFlow Tests».

`scripts/package_smoke.py --executable ABS_PATH --data-dir FRESH_DIR` проверяет frozen distribution, инструменты, Qt UI/local transfer и оба embedded-auth self-tests; data-dir должен быть новым. Затем Windows installer проверяется innounp integrity. В отчёте различаются source tests, native GUI, frozen package и live providers. Не прикладывать реальные токены/профили/подписанные URL.
