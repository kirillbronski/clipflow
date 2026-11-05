# YouTube Music MP3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Music-ссылки всегда дают MP3 лучшей доступной аудиодорожки; папки плейлистов имеют настоящее название.

**Architecture:** Сохранять точный Music-хост в канонической ссылке, общую идентичность YouTube и общий провайдер. Обязательный аудиоформат закреплять в immutable DownloadRequest, а не только в виджете. Название коллекции переносить из probe в PlaylistPosition и SQLite как необязательные метаданные.

**Tech Stack:** Python3.12, PySide6, yt-dlp, FFmpeg/FFprobe, SQLite, pytest/pytest-qt.

**Spec:** docs/superpowers/specs/2026-10-30-youtube-music-mp3-design.md

## Global Constraints

- `music.youtube.com` автоматически только MP3; обычный YouTube сохраняет ручной выбор.
- MP3 320 кбит/с из bestaudio; без видеопотока при наличии audio-only. Никакого обещания улучшить исходный звук.
- Название папки `Sound City [PLO5Q7HxgkOYo]`; нумерация001, безопасные Unicode/пути и защита от коллизий сохраняются.
- Отдельный раздел Music отложен. Существующие файлы/задания не конвертировать/переименовывать автоматически.
- Использовать основной Git checkout на C:, dev; профили не копировать в Git/Drive. Новый Windows2.0.1 EXE/ZIP выдавать в D:/Gdrive/ClipFlow, Mac native отдельно.

## Review Focus

1. Music-хост с credentials/lookalike не обходит проверку URL; обычный YouTube MP4 не становится MP3.
2. Вставка/ручной ввод/batch/playlist mode и дочерние запросы после restart/retry сохраняют обязательный MP3.
3. Очистка Music-ссылки/переход к обычному YouTube возвращает пользовательский video preset без его перезаписи; поздний probe не меняет актуальный формат.
4. Изменение title не меняет ключ дедупликации, старый SQLite playlist без title читается; два одинаковых названия разных плейлистов изолированы.
5. Нет title, длинное/опасное название и частичный сбой не ломают границы пути или нумерацию; проверки MP3 используют настоящий FFprobe.

### Task 1: Сквозной Music-режим, название плейлиста и Windows-поставка

**Files:** domain/models.py, domain/urls.py, application/submission.py, providers/base.py, providers/youtube.py, providers/media.py, domain/paths.py, infrastructure/repository.py, ui/composer.py, ui/i18n.py, version.py внутри src/clipflow; tests/unit/{test_urls,test_submission,test_youtube_provider,test_media_paths}.py, tests/integration/{test_repository,test_media_pipeline}.py, tests/ui/test_submission_dialogs.py; документация CHANGELOG/PROJECT-MEMORY/BUILDING и external Agents pack.

**Interfaces:**
- `ParsedLink.is_music: bool` — вычисляемое свойство по точному hostname; parse_url сохраняет music.youtube.com только для Music-origin, остальные канонизируются по прежним правилам.
- `DownloadRequest.__post_init__` нормализует Music options через dataclasses.replace: format='mp3',max_height=None. Сохранённый preset не изменяется.
- `PlaylistPosition(playlist_id,index,title: str|None=None)` и `ProbeResult(...,collection_title: str|None=None)` расширяются совместимо. Позиция/ID остаются идентичностью; title исключён из request_key.
- SQLite encode сохраняет title, decode старых записей использует defaultNone. URL происхождения Music сохраняется у дочерних треков.
- output_path использует безопасный title + portable playlist identity; при отсутствии title сохраняет прежний fallback. Нумерация по исходному index.

- [ ] Написать RED unit tests: точный Music-host сохраняется; DownloadRequest с Music+MP4/height даёт MP3/None; обычный YouTube+MP4 не меняется; playlist-mode watch?list сохраняет Music; batch даёт MP3 только Music-строкам. Запустить целевые pytest и увидеть FAIL.
- [ ] Реализовать parse_url/is_music/immutable normalization и сохранение origin в SubmissionService. Запустить указанные unit tests: PASS, включая host-spoof/credentials.
- [ ] Написать RED provider/path/storage tests: collection_title='Sound City', оба дочерних Music-запроса MP3, позиции1/2, title survives SQLite/recovery/retry; старые playlist JSON без title читаются; title-only изменение не меняет request_key; одинаковые titles разных IDs дают разные папки. Проверить FAIL, затем реализовать новые optional fields, provider propagation, explicit identity key и SQLite encode. Тесты: PASS.
- [ ] Закрепить title sanitization/fallback/длинные пути тестами, затем изменить output_path; неизменность старых файлов проверить отдельным временным деревом. Нельзя обходить containment или ослаблять collision tests.
- [ ] Написать RED UI tests: ручной ввод и Paste показывают disabled MP3/disabled video quality, batch preview показывает MP3; смена на обычную ссылку/очистка/переключение сервисов возвращает прежний preset, включая folder edits и stale probe. Реализовать эффективный Music state без записи принудительного MP3 в video preset. UI tests: PASS.
- [ ] Native MediaPipeline integration test с настоящим localhost media: результат MP3, только audio,320000bit/s; проверить RED на нынешних192k, затем FFmpeg -b:a320k. Тест источника с audio-only и video formats подтверждает bestaudio selection. MP3 pipeline должен работать и при audio+video fallback без audio-only.
- [ ] Запустить полный `python scripts/check.py` (PASS core95%lines/90%branches/runtime85%) и целевой native Windows UI/clipboard/auth. Проверить результат и причины skips. Реальные пользовательские профили не использовать.
- [ ] Один fresh-context review feature branch по executing-plans; важные замечания исправить одной RED→GREEN серией, minor записать. При обнаружении багов повторить затронутые и полный suite.
- [ ] Обновить версию до2.0.1, CHANGELOG, инструкции и память; commit/push dev. Дождаться exact-SHA Windows/macOS Checks success. Mac native/установку не объявлять проверенными на Windows.
- [ ] Живой тест разрешённого плейлиста PLO5Q7HxgkOYo: настоящий title Sound City, два трека, два MP3 с001/002 и FFprobe audio-only/320k. При внешней блокировке/нет доступа фиксировать unverified, не подменять mocks и не экспортировать сессии.
- [ ] Собрать fresh Windows distribution/EXE/portable2.0.1, embedded-auth/local transfer/tool smoke и installer integrity PASS. Проверить source SHA/dirty=False/хеши; сохранить выдачу и verification report в D:/Gdrive/ClipFlow. Обновление установленной Windows-программы выполнить с локальным backup профиля, проверкой installed source и запуском; прежние2.0.0 артефакты сохранить.
- [ ] Синхронизировать Agents/ClipFlow memory/spec/plan/snapshot/manifest, указать commit/tests/поставку и незакрытые Mac/live ограничения; остановиться после этой разрешённой задачи.

## Проверка полноты

Один сквозной task покрывает spec: forced audio/все пути ввода/стойкость очереди, quality, title/naming, совместимость, реальные проверки и Windows-поставка. ReviewFocus1→URL tests;2→submission/provider/repository;3→UI;4→keys/storage/path;5→path/MediaPipeline. Native inline выбран ранее владельцем; единственный review после реализации. До исполнения требуется подтверждение этого плана по writing-plans.
