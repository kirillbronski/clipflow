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

`scripts/check_coverage.py --reuse` принимает отчёт только для того же runtime fingerprint. В знаменателе все собственные src файлы, включая child-only модули; нет исключений ради процента. CI проверяет Windows и macOS на точном commit.

`scripts/package_smoke.py --executable ABS_PATH --data-dir FRESH_DIR` проверяет frozen distribution, инструменты, Qt UI/local transfer и оба embedded-auth self-tests; data-dir должен быть новым. Затем Windows installer проверяется innounp integrity. В отчёте различаются source tests, native GUI, frozen package и live providers. Не прикладывать реальные токены/профили/подписанные URL.
