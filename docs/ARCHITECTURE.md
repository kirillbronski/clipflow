# Архитектура ClipFlow 2.0

`run.py` и `clipflow.__main__` вызывают один `ui.bootstrap`. Старый Tk runtime удалён после сопоставления 11 legacy scripts с настоящими pytest сценариями (`tests/legacy-parity.json`). Frozen entry использует тот же bootstrap.

- `domain`: неизменяемые ParsedLink/DownloadRequest/DownloadOptions/Job, URL identity, безопасные имена, события и cancellation token; без Qt и сети.
- `application`: submission, scheduler, порты и общий Instagram rate policy. Один executor slot; события привязаны к attempt_id. Поздние события старой попытки не меняют текущую запись. Cancel/close ждут teardown ACK.
- `providers`: YouTube/Music и GetCourse discovery, Instagram posts/profiles, общий MediaPipeline/FFmpeg. Raw metadata/CDN URL живут только в памяти. Коллекции создают отдельные дочерние запросы, фильтры и выбор не меняют исходную нумерацию.
- `infrastructure`: SQLite jobs/recovery, атомарные settings, persisted IG cooldown, native auth gateway и отдельный QtWebEngine child, DPAPI/Keychain. Сохранённые задания не содержат паролей/cookies/подписанных CDN URL.
- `ui`: presenter, модель/delegate списка и Qt Widgets, composer, batch/selection/accounts/settings, перевод и палитра. Рабочие потоки посылают события; UI изменяется в Qt thread.

Правило зависимостей (проверяется `tests/unit/test_layers.py`): `domain` ни от кого; `application` от `domain`; `providers` от `domain` и `application`; `infrastructure` от всех, кроме `ui`; `ui` от `domain`, `application`, `ui`. Точки сборки, которым разрешено всё: `ui/bootstrap.py`, `ui/self_test.py`, `infrastructure/auth_process/__main__.py` и `window.py` (отдельный GUI-процесс входа).

Части крупных объектов: окно `ui/window.py` собирает `Sidebar` (`ui/sidebar.py`), `QueuePanel` (`ui/queue_panel.py`), меню (`ui/window_menus.py`) и диалоги (`ui/window_dialogs.py`). `WorkbenchPresenter` — фасад над `ProbeCache` (`application/probe_cache.py`), `ClearingController`, `AccountsController`, `TitleNamer` (`ui/presenter_*.py`); правила истории — `application/history.py`. `MediaPipeline.save` — сценарий над `media_plan.py` (имя и идентичность), `processes.py`, `conversion.py` (`MediaTools`), `publishing.py`. Тела рабочих потоков — функции `infrastructure/work.py`; классы QThread только вызывают их. Коды сбоев сгруппированы в `domain/failures.py`; ошибки правил очереди — `application/errors.py` (`JobRuleError`).

Процент 100 означает передачу байтов, но завершение устанавливается только после обработки, проверки файлов и записи результата. Телеметрия ограничена примерно двумя обновлениями в секунду; скорость измеряется по изменению байтов. HTTP resume сохраняет partial state; сбой/повтор использует проверенные готовые файлы. SQLite и файловая система не являются общей транзакцией.

История и очистка записей отделены от удаления файлов. Перед unlink проверяется весь выбор: terminal, idle, recorded files, containment, отсутствие symlink/junction/directories. Рекурсивное удаление результатов запрещено.
