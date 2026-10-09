<p align="center">
  <img src="source/clipflow.png" width="88" alt="ClipFlow icon">
</p>
<h1 align="center">ClipFlow</h1>
<p align="center"><strong>Ваши видео. В вашей папке.</strong><br>Приложение для скачивания видео, аудио и фотографий с YouTube, Instagram и GetCourse.</p>
<p align="center">
  <a href="https://github.com/kirillbronski/clipflow/actions/workflows/check.yml"><img src="https://github.com/kirillbronski/clipflow/actions/workflows/check.yml/badge.svg" alt="Checks"></a>
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white" alt="Python 3.12">
  <img src="https://img.shields.io/badge/Windows-x64-0078D4" alt="Windows x64">
  <img src="https://img.shields.io/badge/macOS-Apple%20Silicon-222222?logo=apple" alt="macOS Apple Silicon">
</p>
<p align="center"><a href="#возможности">Возможности</a> · <a href="#интерфейс">Интерфейс</a> · <a href="docs/DEVELOPMENT.md">Запуск исходников</a> · <a href="docs/BUILDING.md">Сборка</a> · <a href="https://github.com/kirillbronski/clipflow/releases">Релизы</a></p>

## Возможности

| Сервис | Что можно сохранить |
|---|---|
| **YouTube** | Отдельные видео и плейлисты, MP4 или MP3, выбор качества. |
| **Instagram** | Reels, посты, фотографии и карусели; все медиа или только видео/фото; полное описание TXT/MD. |
| **GetCourse** | Видео уроков и плееров, выбор материалов урока, скачивание с доступом вашего аккаунта. |

- Очередь загрузок с прогрессом, скоростью и оставшимся временем.
- Пауза, продолжение, отмена и повторная попытка в строке задания.
- Проверка доступного качества и переключатель автоматического скачивания.
- Отдельные папки сервисов, короткие имена файлов и запоминание настроек.
- Три цветовые темы по сервисам, русский и английский интерфейс.
- Встроенные окна входа YouTube и Instagram; отдельное хранение их сессий.
- Защита сохранённых данных через Windows DPAPI или macOS Keychain.

## Интерфейс

Скриншоты сделаны на macOS из общего кода приложения. На Windows используются системные шрифты, диалоги и сочетания клавиш Windows.

### YouTube
![ClipFlow — YouTube на macOS](docs/screenshots/youtube-macos.png)

### Instagram
![ClipFlow — Instagram на macOS](docs/screenshots/instagram-macos.png)

### GetCourse
![ClipFlow — GetCourse на macOS](docs/screenshots/getcourse-macos.png)

## Установка

Готовые установщики публикуются в [GitHub Releases](https://github.com/kirillbronski/clipflow/releases): Windows — EXE, macOS — DMG. Для готового приложения отдельно устанавливать Python, FFmpeg и Node.js не требуется.

Текущие проверенные сборки 1.8.4 были выпущены до объединения исходников. Общая кодовая база проходит отдельные проверки Windows/macOS; статус виден в значке Checks. Новые установщики нужно собирать из нужного коммита на соответствующей системе.

**Платформы:** Windows x64; готовая macOS-сборка 1.8.4 — Apple Silicon, macOS 27 и новее. Intel Mac пока не входит в выпускаемую сборку. Локальная macOS-сборка имеет ad-hoc подпись и не нотарифицирована Apple.

## Разработка

Одна папка `source/` используется для обеих платформ. Основной файл — **`source/clipflow.py`**. Поведение скачивания и интерфейс меняются здесь один раз; системные отличия находятся в `source/platform_support.py`.

```text
clipflow/
├── source/                 # общий код и ресурсы приложения
│   ├── clipflow.py         # интерфейс, очередь, скачивание
│   ├── platform_support.py# системные пути, шифрование, сочетания клавиш
│   └── _internal/          # CustomTkinter с локальным исправлением вкладок
├── assets/icons/           # значки установщиков
├── packaging/
│   ├── windows/            # установщик Windows
│   └── macos/              # PyInstaller spec для macOS
├── scripts/                # проверки и нативная сборка
├── tests/                  # регрессионные проверки
├── docs/                   # инструкции и скриншоты
└── run.py                  # запуск из исходников
```

После установки зависимостей:

```sh
python run.py
python scripts/check.py
python scripts/build.py
```

Подробно: [настройка окружения](docs/DEVELOPMENT.md), [сборка установщиков](docs/BUILDING.md), [порядок работы с Git](CONTRIBUTING.md).

## Доступ к контенту

Для закрытых материалов нужен аккаунт с доступом. Instagram и Google могут требовать вход или ограничивать встроенные браузеры; наличие сохранённой сессии не гарантирует доступ к каждому материалу. Скачивайте только контент, который вы вправе сохранять.

## Компоненты и лицензирование

ClipFlow использует yt-dlp, CustomTkinter, PySide6/Qt, FFmpeg, Node.js и другие компоненты. Их лицензии перечислены в [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md). Лицензия на собственный код ClipFlow пока не выбрана; публичность репозитория сама по себе не предоставляет отдельной лицензии на его использование и распространение.
