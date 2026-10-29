# Архитектура ClipFlow 2.0

`run.py` и `clipflow.__main__` вызывают один `ui.bootstrap`. Старый Tk runtime удалён после сопоставления 11 legacy scripts с настоящими pytest сценариями (`tests/legacy-parity.json`). Frozen entry использует тот же bootstrap.

- `domain`: неизменяемые ParsedLink/DownloadRequest/DownloadOptions/Job, URL identity, безопасные имена, события и cancellation token; без Qt и сети.
- `application`: submission, scheduler, порты и общий Instagram rate policy. Один executor slot; события привязаны к attempt_id. Поздние события старой попытки не меняют текущую запись. Cancel/close ждут teardown ACK.
- `providers`: YouTube/Music и GetCourse discovery, Instagram posts/profiles, общий MediaPipeline/FFmpeg. Raw metadata/CDN URL живут только в памяти. Коллекции создают отдельные дочерние запросы, фильтры и выбор не меняют исходную нумерацию.
- `infrastructure`: SQLite jobs/recovery, атомарные settings, persisted IG cooldown, native auth gateway и отдельный QtWebEngine child, DPAPI/Keychain. Сохранённые задания не содержат паролей/cookies/подписанных CDN URL.
- `ui`: presenter, модель/delegate списка и Qt Widgets, composer, batch/selection/accounts/settings, перевод и палитра. Рабочие потоки посылают события; UI изменяется в Qt thread.

Процент 100 означает передачу байтов, но завершение устанавливается только после обработки, проверки файлов и записи результата. Телеметрия ограничена примерно двумя обновлениями в секунду; скорость измеряется по изменению байтов. HTTP resume сохраняет partial state; сбой/повтор использует проверенные готовые файлы. SQLite и файловая система не являются общей транзакцией.

История и очистка записей отделены от удаления файлов. Перед unlink проверяется весь выбор: terminal, idle, recorded files, containment, отсутствие symlink/junction/directories. Рекурсивное удаление результатов запрещено.
