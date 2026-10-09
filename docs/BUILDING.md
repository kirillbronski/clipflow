# Сборка установщиков

Источник версии один: `source/version.py`. Исходники Windows и macOS общие; сборку выполняют на целевой системе. Сначала настройте окружение из DEVELOPMENT.md и выполните `python scripts/check.py`.

## Windows x64

Установите Inno Setup 6. Компилятор ищется в PATH и стандартной папке установки; альтернативный путь задаётся переменной `INNO_SETUP_COMPILER`. FFmpeg и FFprobe должны быть настоящими бинарниками, а не ярлыками или Chocolatey shim-файлами.

```powershell
.venv\Scripts\python.exe scripts/build.py
```

Результат в `outputs/`: `ClipFlow-Setup-VERSION.exe` и `ClipFlow-VERSION-Windows-x64-portable.zip`. Portable ZIP нужно распаковать целиком. Сохранён прежний AppId установщика, поэтому обновление устанавливается поверх ClipFlow, сохраняя пользовательские профили.

Без Inno Setup можно собрать portable ZIP:

```powershell
.venv\Scripts\python.exe scripts/build.py --portable-only
```

В GitHub Actions доступен ручной workflow **Build Windows**: он собирает общий код на Windows и прикрепляет EXE/ZIP как артефакты. Публикация в Releases выполняется отдельно после проверки.

## macOS Apple Silicon

Сборка ожидает FFmpeg, FFprobe и Node в `/opt/homebrew/bin`. Python должен быть arm64 с работающим Tk.

```sh
.venv/bin/python scripts/build.py
```

Результат в `outputs/`: `.app`, `ClipFlow-VERSION-macOS-arm64.dmg` и ZIP приложения. Скрипт проверяет подпись, встроенные окна входа и контрольную сумму DMG. Временная копия для DMG удаляется после упаковки. `.app` в outputs — результат сборки; после установки и архивирования её следует убрать, чтобы в Launchpad не появлялись дубликаты.

Минимальная система текущей сборки — macOS 27. Для более ранней системы нужна отдельная проверка Python и всех включённых бинарников; одного изменения Info.plist недостаточно. Подпись ad-hoc не заменяет Developer ID и notarization.

## Публикация

Сначала проверки и сборки, затем Git-тег версии и GitHub Release. В Assets помещаются EXE, DMG и при необходимости portable ZIP. Установщики, `.venv`, профили входа и временные результаты в Git не добавляются.
