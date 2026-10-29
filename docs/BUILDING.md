# Нативная сборка 2.0

Версия: `src/clipflow/version.py`. Python3.12, PyInstaller, FFmpeg/FFprobe/Node и лицензии. Сначала `python scripts/check.py`; затем **на целевой ОС** `python scripts/build.py`. Каждый запуск создаёт fresh UUID stage в outputs/2.0.0; установленную папку никогда не накладывать поверх поставки.

Windows x64: Inno Setup6 в PATH/стандартной папке или INNO_SETUP_COMPILER. Chocolatey shims не заменяют настоящие FFmpeg/FFprobe. Скрипт ограничивает DLL/PATH окружение и явно передаёт tool paths. Результат: версионные Setup EXE и portable ZIP (распаковать целиком). `--portable-only` пропускает компиляцию установщика. AppId прежний, данные LocalAppData остаются отдельно.

Mac arm64: `python scripts/build.py` на Apple Silicon; FFmpeg/FFprobe/Node в PATH/Homebrew. .app, DMG, APP ZIP, ad-hoc codesign и hdiutil verify. Deployment minimum27; runner15 binary smoke не заменяет запуск из DMG через Launch Services27. Полный [T16a](MAC-T16A.md) остаётся обязательным для Mac выпуска.

Упаковка включает QtWebEngine/resources/translations, yt-dlp JS assets, FFmpeg/FFprobe/Node и third-party notices. В поставке не должно быть plaintext project source, tests, caches, logs, пользовательских настроек/сессий или uninstallers исходной установки. Tk больше не нужен: соответствующий runtime retired после parity.

Smoke выполняет реальный frozen Qt UI/local media и оба protected auth self-tests на synthetic profiles. Windows EXE дополнительно проверить innounp integrity; metadata build-report source_commit/dirty=False, размеры и SHA256SUMS. Dirty-сборки диагностические. CI workflow Build native Qt candidates принимает target all/windows/macos; общий source CI обеих ОС сохраняется.

Выдача владельцу: D:/Gdrive/ClipFlow, EXE/portable ZIP, SHA256SUMS и verification report. Предыдущие проверенные кандидаты сохранять отдельно, не перезаписывать неизвестный файл. Mac DMG до T16a обозначать T15 candidate. GitHub Release и установка приложения — отдельные действия, не следствие появления файла в Drive.
