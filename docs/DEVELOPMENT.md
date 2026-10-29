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

Для экспериментов задать CLIPFLOW_DATA_DIR на отдельную временную папку. Реальные профили не переносить в репозиторий. Runtime не импортирует Tk/CustomTkinter, `--qt-preview` удалён; оба entrypoint запускают Qt. Реальные аккаунты вводит владелец.

См. ARCHITECTURE, TESTING, BUILDING и PROJECT-MEMORY. Изменения проверяются перед commit/push; точный SHA обязательных Windows/macOS Checks фиксируется в handoff. Mac завершение вынесено в T16a.
