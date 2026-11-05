# Linux как третья платформа

Статус: дизайн подтверждён владельцем 2 ноября 2026; спецификация ждёт проверки владельцем.

## Контекст

ClipFlow собирается из одного исходника под Windows и macOS. Интерфейс (PySide6/Qt), загрузки (yt-dlp, instaloader) и FFmpeg общие. Платформенный код небольшой и разбросан по нескольким местам:

- `infrastructure/platform.py`: папка данных, шифрование (DPAPI на Windows, Keychain + Fernet на Mac). На прочих ОС `protect()` падает с `auth_protection_failed`.
- `infrastructure/keep_awake.py`: `SetThreadExecutionState` / `caffeinate -w`.
- `infrastructure/auth.py` (`browser_source`): пути профилей Яндекс.Браузера и Opera GX.
- `ui/bootstrap.py` (`_binary`) и `scripts/package_config.py` (`resolve_tool`): поиск ffmpeg/ffprobe/node в `.runtime/<os>/bin`.
- `ui/themes.py`: шрифт; `ui/window_dialogs.py`: подпись «Показать в Finder / Проводнике».
- `scripts/build.py`: отказывается работать не на Windows/macOS; упаковка через Inno Setup и DMG.
- CI (`check.yml`, `build.yml`): только `windows-latest` и `macos-15`.

## Цель

Одинаковый функционал на Linux. Пользователь Fedora или Ubuntu скачивает один файл и ставит программу двойным кликом через графический мастер, как это сделано у AmneziaVPN (Qt Installer Framework, `.run`).

## Решения владельца

- Публичная раздача: установщик должен работать на чужих системах, в GNOME и KDE, на Wayland и X11.
- Поддержка: Ubuntu 22.04+ и Fedora 40+, архитектуры x86-64 и ARM64.
- Если Secret Service недоступен, вход работает, но данные входа не сохраняются, и пользователь видит предупреждение.
- Формат: PyInstaller + Qt Installer Framework → `.run`, плюс portable `tar.gz`.
- Ручная проверка позже: x86-64 проверяет владелец на ПК с Fedora 44, ARM64 — на Ubuntu в Parallels на Mac. CI не заменяет ручную проверку.

## Платформенный код

Всё остаётся в `src/clipflow/infrastructure` (и мелкие развилки в `ui`). Каждая Linux-ветка тестируется на любой ОС через подмену системы, как уже сделано в `KeepAwake(system=...)`.

### Папка данных

`data_directory()` на Linux: `$XDG_DATA_HOME/ClipFlow`, если переменная задана и путь абсолютный, иначе `~/.local/share/ClipFlow`. `CLIPFLOW_DATA_DIR` по-прежнему имеет приоритет.

### Пароли и сессии

- Та же схема, что на Mac: ключ Fernet хранится в системном хранилище под тем же `key_namespace()`, данные шифруются Fernet.
- Бэкенд: `keyring.backends.SecretService.Keyring` (зависимость `secretstorage`, ставится только на Linux маркером окружения в requirements).
- Если бэкенд не загружается, D-Bus или хранилище недоступны, либо хранилище заблокировано и не открылось, `protect()` поднимает `OSError('auth_secret_store_unavailable')`. Прочие сбои по-прежнему дают `auth_protection_failed`. Ключи и секреты в сообщения не попадают.
- Слой входа, получив `auth_secret_store_unavailable`, держит данные входа только в памяти до закрытия программы и показывает предупреждение через i18n (ru/en): данные входа не будут сохранены, установите или разблокируйте хранилище паролей (GNOME Keyring / KWallet). Повторный запуск снова пробует хранилище.
- Windows и macOS не меняются.

### Не засыпать во время загрузок

На Linux `hold()` запускает
`systemd-inhibit --what=sleep:idle --who=ClipFlow --why=<текст> --mode=block tail --pid=<pid> -f /dev/null`.
Блокировка снимается сама, когда ClipFlow завершается, даже аварийно (аналог `caffeinate -w`). `release()` завершает процесс так же, как на Mac. Если `systemd-inhibit` отсутствует, действие молча пропускается.

### Cookies браузеров

- Яндекс.Браузер на Linux: `~/.config/yandex-browser` (как профиль Chromium).
- Opera GX под Linux не выпускается: на Linux её нет в списке браузеров (`domain/models.py`, `ui/accounts.py`, сопоставление имён в `auth.py`). Сохранённый ранее выбор `opera_gx` на Linux считается недопустимым и сбрасывается на выбор пользователя без падения.
- Остальные браузеры yt-dlp находит сам.

### Мелочи

- `_binary` и `resolve_tool`: папка `.runtime/linux/bin`.
- Шрифт: на Linux не задаётся явно, используется системный шрифт Qt.
- Пункт меню строки: новая подпись `row_menu.reveal_linux` («Показать в папке» / «Show in folder»).

### Окно входа (QtWebEngine) и песочница

- Ubuntu 24.04+ ограничивает непривилегированные user namespaces через AppArmor, и песочница Chromium в QtWebEngine падает.
- Процесс окна входа (`auth_process`) перед созданием QtWebEngine читает `/proc/sys/kernel/apparmor_restrict_unprivileged_userns`. Если там `1`, только в этом процессе ставится `QTWEBENGINE_DISABLE_SANDBOX=1`. Если файла нет или там `0`, песочница остаётся.
- Основной процесс страниц не открывает и не затрагивается.
- Профиль AppArmor не ставим: он требует прав администратора.

## Сборка и установщик

### Сборка

- `scripts/build.py` принимает `linux`. Архитектура определяется по `platform.machine()`: `x86_64` или `aarch64` (`arm64` нормализуется в `aarch64`); другие архитектуры отклоняются.
- PyInstaller собирает папку `ClipFlow/` по `packaging/linux/ClipFlow.spec`. Общие входы берутся из `spec_inputs(root, 'linux')`, для Linux добавляется `keyring.backends.SecretService`.
- В пакет кладутся ffmpeg/ffprobe (статические сборки той же лицензии, что Windows-сборка; лицензия в `licenses/`) и официальный Node под архитектуру с лицензией, как сейчас.
- Проверка glibc: сборка падает, если какой-либо ELF-файл пакета требует символов `GLIBC_` новее 2.35. Проверяется по версиям символов (`objdump -T` или `readelf`), а не по имени ОС сборки.

### Установщик QtIFW

Файлы `packaging/linux/installer/`: `config/config.xml`, `packages/<id>/meta/package.xml`, `installscript.qs`, переводы мастера (ru/en).

- Каталог по умолчанию: `~/.local/opt/ClipFlow`. Прав администратора не требуется.
- `installscript.qs` создаёт `~/.local/share/applications/clipflow.desktop` (Name, Exec с абсолютным путём, Icon, Categories=AudioVideo;Network;, StartupWMClass) и иконку concept1 в `~/.local/share/icons/hicolor/<size>/apps/clipflow.png`, затем обновляет кеш меню, если доступен `update-desktop-database`.
- Деинсталлятор `maintenancetool` с ярлыком в меню. Удаление убирает программу, ярлыки и иконки, но не трогает `~/.local/share/ClipFlow`.
- Запуск установщика новой версии поверх установленной обновляет программу; данные пользователя сохраняются.

### Артефакты (для каждой архитектуры)

- `ClipFlow-<версия>-Linux-<arch>-Setup.run`
- `ClipFlow-<версия>-Linux-<arch>-portable.tar.gz` (папка `ClipFlow/` с сохранёнными правами запуска)
- `build-report.json`, `package-report.json`, `SHA256SUMS.txt`
- `INSTALL.txt` (ru/en) с инструкцией, включая «Разрешить запуск как программу», если двойной клик не сработал.

### Автопроверка пакета

Внутри `build.py`, если не задан `--skip-smoke`:

1. Смоук собранного `ClipFlow/ClipFlow` через `package_smoke.py` (`QT_QPA_PLATFORM=offscreen`).
2. Тихая установка `.run` во временную папку в консольном режиме QtIFW; проверка `.desktop` (обязательные ключи, Exec указывает на существующий файл) и иконки; смоук установленного приложения. Ярлыки ставятся во временный `XDG_DATA_HOME`, а не в профиль сборщика.
3. Удаление через `maintenancetool` в консольном режиме: программы и ярлыков нет, тестовая папка данных на месте.

### QtIFW

- x86-64: официальная сборка QtIFW с download.qt.io, версия закреплена, SHA256 проверяется.
- ARM64: официальной сборки нет. CI собирает QtIFW закреплённой версии из исходников на `ubuntu-22.04-arm` и кеширует результат по версии. `build.py` берёт компилятор из `QTIFW_BINARYCREATOR` или `PATH` и выдаёт понятную ошибку, если его нет (флаг `--portable-only` пропускает установщик, как на Windows).

## CI

### `check.yml`

- В матрицу добавляется `ubuntu-22.04`; шаг ставит системные библиотеки Qt (xcb/xkbcommon/EGL/OpenGL/fontconfig/dbus).
- `python scripts/check.py` с теми же порогами покрытия.
- Платформенный тест Secret Service: `dbus-run-session` + `gnome-keyring-daemon` с разблокированной тестовой связкой. Проверяются запись, чтение и удаление тестового ключа в namespace `ClipFlow Tests`, а также сценарий без хранилища → `auth_secret_store_unavailable`. На Windows и macOS тест пропускается.

### `build.yml`

- В выбор `target` добавляется `linux`. Для `all` матрица включает `ubuntu-22.04` и `ubuntu-22.04-arm`.
- В артефакты добавляются `.run`, `tar.gz` и отчёты.
- Если `ubuntu-22.04-arm` недоступен для репозитория, ARM-сборка отмечается как недоступная, а не успешная, и это сообщается владельцу.

## Тесты

Модульные, работают на любой ОС:

- `data_directory` на Linux: с абсолютным `XDG_DATA_HOME`, с относительным (игнорируется), без него.
- `protect` на Linux с подменённым keyring: шифрование и расшифровка, отсутствие бэкенда/D-Bus/заблокированное хранилище → `auth_secret_store_unavailable`, повреждённые данные → `auth_protection_failed`; секреты не попадают в текст ошибки.
- Поведение входа при `auth_secret_store_unavailable`: данные в памяти, предупреждение показано, на диск ничего не пишется.
- `KeepAwake(system='linux')`: точная команда, завершение процесса, отсутствие `systemd-inhibit`.
- `browser_source('yandex')` на Linux; отсутствие Opera GX в списке Linux; сброс сохранённого `opera_gx`.
- Решение о песочнице окна входа: значения `1`, `0`, файла нет.
- `_binary`/`resolve_tool` с `.runtime/linux/bin`; шрифт; ключ подписи «Показать в папке».
- Конфигурация пакета: имена артефактов по архитектуре, нормализация `arm64`, отказ на неизвестной архитектуре, разбор проверки glibc на примерах вывода, содержимое `.desktop`, корректность XML-конфигов QtIFW.

## Правила проекта

- `AGENTS.md`: Linux — третья платформа; данные в `~/.local/share/ClipFlow`; слияние `dev` → `main` только после зелёных проверок Windows, macOS **и Linux** для того же коммита; Linux-пакеты собираются на Linux; ручная проверка не выводится из CI.
- `docs/PROJECT-MEMORY.md`: состояние Linux-работ и ссылки на спецификацию, план и чек-лист.

## Ручная проверка

`docs/LINUX-QA.md` — чек-лист с колонками «Fedora 44 x86-64 (владелец)» и «Ubuntu ARM64 (Parallels на Mac)». В каждой строке: результат, дата, коммит сборки, замечания.

1. Подготовка: образ Ubuntu ARM64 для Parallels, где взять сборку (артефакты CI или `D:/Gdrive/ClipFlow`), сверка SHA256.
2. Установка двойным кликом по скачанному `.run`. Записать, понадобилось ли «Разрешить запуск», и проверить вариант с обёрткой `.tar`. Это закрывает открытый вопрос ниже.
3. Ярлык и иконка в меню, запуск, светлая и тёмная тема, Wayland и X11 (сеанс входа).
4. Загрузки: YouTube, YouTube Music → MP3, Instagram с соблюдением `INSTAGRAM-RATE-LIMITS.md`, GetCourse.
5. Окно входа открывается и вход проходит; на Ubuntu 24.04+ срабатывает режим без песочницы, на Fedora песочница включена.
6. Хранилище паролей: вход сохраняется после перезапуска; без хранилища или с заблокированным показывается предупреждение, программа работает.
7. Компьютер не засыпает во время длинной загрузки.
8. Обновление поверх предыдущей версии; удаление оставляет `~/.local/share/ClipFlow`.
9. Portable `tar.gz` запускается без установки.

Пока строки не заполнены, Linux-сборка считается «собрана и проверена в CI, вручную не проверена».

## Открытые вопросы

- Нужна ли обёртка `.tar` вокруг `.run`, чтобы двойной клик работал без «Разрешить запуск». Решается по пункту 2 ручной проверки.
- Доступность `ubuntu-22.04-arm` для этого репозитория. Выясняется при первом запуске `build.yml`.

## Вне рамок

- Ручная проверка (выполняет владелец позже), слияние в `main`, публичный релиз.
- Flatpak, AppImage, `.deb`/`.rpm`, автообновление, подпись пакетов, профиль AppArmor.
- Архитектуры, кроме x86-64 и ARM64.
