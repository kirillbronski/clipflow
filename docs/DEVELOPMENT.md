# Разработка

Общий пакет `src/clipflow`, Python 3.12. Ветки dev/main; перед работой git status/fetch/pull --ff-only, не стирать локальные изменения.

```sh
python -m venv .venv
# активировать .venv для своей ОС
python -m pip install -r requirements-dev.txt
python run.py
python scripts/check.py
```

requirements-dev устанавливает editable пакет и pytest. Для исходников нужны FFmpeg, FFprobe и Node в PATH либо `.runtime/<windows|macos>/bin`; точные пути можно задавать CLIPFLOW_FFMPEG_PATH/CLIPFLOW_FFPROBE_PATH/CLIPFLOW_NODE_PATH при сборке. Не копировать .venv между машинами.

## Стиль кода

Весь Python-код форматируется и проверяется ruff (версия закреплена в `pyproject.toml`, ставится из requirements-dev): длина строки 100, одинарные кавычки, правила E/W/F/I/B/UP/SIM. Перед коммитом:

```sh
python -m ruff format .
python -m ruff check --fix .
```

`scripts/check.py` начинает с `ruff format --check` и `ruff check` и останавливается при замечаниях — то же происходит в CI. `# noqa` допускается только с кодом правила и причиной. Механическое форматирование 30.10.2026 скрыто из `git blame` списком `.git-blame-ignore-revs`; подключить локально: `git config blame.ignoreRevsFile .git-blame-ignore-revs`. Локальные правки или stash, сделанные до форматирования (`4cec26d`), переносить так: создать ветку от `4cec26d^`, применить на ней правки, выполнить `python -m ruff format .`, закоммитить и только затем rebase на актуальный `dev` — иначе конфликты будут почти в каждом файле.

Для экспериментов задать CLIPFLOW_DATA_DIR на отдельную временную папку. Реальные профили не переносить в репозиторий. Runtime не импортирует Tk/CustomTkinter, `--qt-preview` удалён; оба entrypoint запускают Qt. Реальные аккаунты вводит владелец.

См. ARCHITECTURE, TESTING, BUILDING и PROJECT-MEMORY. Изменения проверяются перед commit/push; точный SHA обязательных Windows/macOS Checks фиксируется в handoff. Mac завершение вынесено в T16a.
