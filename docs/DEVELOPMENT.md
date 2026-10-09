# Запуск исходников

Рабочую копию храните локально, вне Google Drive/OneDrive. На каждом компьютере — отдельный `git clone`, обмен изменениями через GitHub. Установщики и резервные архивы можно хранить в Drive.

## Получить код

```sh
git clone --branch dev git@github.com:kirillbronski/clipflow.git
cd clipflow
```

Без SSH можно клонировать `https://github.com/kirillbronski/clipflow.git`.

Рабочая ветка на обеих ОС — `dev`; `main` содержит проверенные изменения. Перед работой на чистой `dev` выполните `git pull --ff-only`. Правки отправляйте в `origin/dev`; слияние в `main` — только после проверок по CONTRIBUTING.md.

## Windows

Установите Python 3.12 x64 с Tk (обычная установка python.org), FFmpeg/FFprobe и Node.js. Добавьте бинарники в PATH либо положите все три EXE в `.runtime/windows/bin/`. Эта папка исключена из Git. Можно указать отдельную папку через `CLIPFLOW_BIN_DIR`; остальные бинарники будут найдены в PATH.

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe run.py
```

PowerShell activation не требуется. Все настройки, GetCourse-профиль и сессии теперь сохраняются в `%LOCALAPPDATA%\ClipFlow`.

Перед первым запуском новой версии на компьютере с прежней установкой найдите прежнюю папку данных приложения и сохраните её резервную копию. Затем выполните `.\.venv\Scripts\python.exe scripts/migrate_windows_data.py --source "ПОЛНЫЙ_ПУТЬ_К_ПРЕЖНЕЙ_ПАПКЕ_ДАННЫХ"`. Укажите именно папку с `settings.json` и/или `getcourse-profile.dat`, а не папку исходников или установленного EXE. Команда копирует только эти файлы, не перезаписывает существующие данные ClipFlow и сохраняет оригиналы. Закройте приложение на время переноса. Защищённый профиль переносится на том же Windows-компьютере под тем же пользователем; перенос DPAPI-данных с другого компьютера не поддерживается.

## macOS

Установите Python 3.12 с Tk, FFmpeg и Node.js. При использовании Homebrew:

```sh
brew install python@3.12 python-tk@3.12 ffmpeg node
/opt/homebrew/bin/python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -c 'import tkinter; print(tkinter.TkVersion)'
.venv/bin/python run.py
```

Если Homebrew установил модуль Tk отдельно и команда проверки не находит `_tkinter`, добавьте его в окружение:

```sh
cp /opt/homebrew/opt/python-tk@3.12/libexec/_tkinter*.so .venv/lib/python3.12/site-packages/
```

Настройки и сессии: `~/Library/Application Support/ClipFlow`. Ключ шифрования хранится в login Keychain; запрос доступа macOS подтверждается пользователем.

## IDE

Откройте корень проекта, выберите Python из `.venv` и запускайте `run.py` либо `source/clipflow.py`. Рабочая директория — корень репозитория. Перед каждой правкой пересобирать установщик не требуется.

## Проверки

```sh
python scripts/check.py
```

Сценарий использует временные профили, локальные тестовые данные и имитацию сетевых ответов. Он не выполняет вход в реальные аккаунты. Проверка окон входа отдельно:

```sh
python run.py --auth-self-test PATH_TO_TEMP_PROFILE
python run.py --instagram-auth-self-test PATH_TO_ANOTHER_TEMP_PROFILE
```

Для изоляции Keychain/путей установите `CLIPFLOW_DATA_DIR` в ту же временную папку перед отдельной проверкой. `scripts/check.py` делает это автоматически. Реальные проверки публичного контента выполняются отдельно от offline-тестов.
