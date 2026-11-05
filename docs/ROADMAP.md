# Статус ClipFlow 2.0

## Реализовано

Единственный Qt runtime; RU/EN и dark/light/system; immutable requests, одна очередь, batch/выбор коллекций, progress/pause/resume/cancel/retry; SQLite recovery paused; безопасная история/удаление; DPAPI/Keychain и отдельный встроенный auth process. Форматы MP4/MKV/WebM/MP3, Instagram фото/описания; GetCourse несколько видео.

## Experimental / требуется подтверждение

Live доступ к площадкам и закрытым материалам, IG profile10/50/all и лимиты upstream. Сетевые блокировки и отсутствие сессии не являются успехом. Windows установка и Mac native/package/Launch Services приёмка выполнены; личные/live пункты T16a **открыты**. GitHub macOS15 и запуск binary не доказывают установку через Launch Services на macOS27.

## T16a — на Mac

Полный чек-лист: [MAC-T16A.md](MAC-T16A.md). Native Cocoa/Retina/Command, auth/Keychain, очередь/recovery/process groups, live разрешённые материалы, чистая .app/DMG/ZIP, codesign/hdiutil, Finder/Launch Services27, обновление с сохранением профиля и одна установленная копия; затем SHA/report/память.

## Далее

Параллельные загрузки с отдельной политикой лимитов; автоматическое обновление; Developer ID/notarization; другие платформы/сервисы после проверки контрактов. Spotify рассматривается только как источник метаданных/сопоставления, не как прямое скачивание аудио.
