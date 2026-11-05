# Подпроект 3: архитектура и разбор крупных объектов

Статус: дизайн подтверждён владельцем 31 октября 2026; спецификация ждёт проверки владельцем.

## Контекст

Третий из четырёх подпроектов чистки (1 — ruff, 2 — UX и тексты, 3 — архитектура, 4 — ревизия тестов). Состояние на `dba7e4f`: 9 668 строк в `src/clipflow`; крупнее всех `ui/window.py` (896), `ui/composer.py` (629), `ui/presenter.py` (539), `ui/i18n.py` (481, каталог текстов), `providers/media.py` (463). `ruff --select C901,BLE001`: 18 функций сложнее 10 и 25 `except Exception`.

Найдено:

- `domain/paths.py` ссылается на `providers.base.MediaItem` (домен знает о провайдерах).
- `infrastructure/auth_process` импортирует `ui.themes`/`ui.i18n`; `ui/accounts.py` берёт `BROWSERS` из `infrastructure.auth`; `ui/self_test.py` — провайдеров.
- `WorkbenchPresenter._command` определяет код ошибки по тексту `ValueError` (`'Source changed'`, `'Cooldown'`); исправление текста исключения молча меняет показанную ошибку.
- Классификация кодов сбоев живёт в `ui/job_status.py`, хотя это знание о домене (отложено сюда подпроектом 2).
- `MainWindow.__init__` — 240 строк; `WorkbenchPresenter` смешивает семь обязанностей; `MediaPipeline.save` — 85 строк со всеми этапами сразу.
- `tests/unit/test_executor_workers.py` завязан на приватные `_Worker`/`_ProbeWorker`/`_TitleWorker` (отложено сюда подпроектом 1).

## Цель

Зависимости между слоями однонаправленные и проверяются тестом; крупные объекты разбиты по обязанностям; в ruff включены `C901` (порог 10) и `BLE001`, без временных исключений. Поведение программы не меняется.

## Решения владельца

- Глубина умеренная: без отдельного слоя use cases, презентер остаётся на Qt, пакеты не перестраиваются целиком. Публичные методы и сигналы `WorkbenchPresenter` и атрибуты `MainWindow`, которыми пользуются тесты, сохраняются (делегированием).
- Порядок — «храповик и срезы»: сначала правила включаются с временными пометками, затем каждый срез снимает свои.
- Сборки Windows и Mac не делаются до конца всех четырёх подпроектов; версия не поднимается. Работа прямо в `dev`. Финальное ревью — субагент opus, effort high.

## Слои и правило зависимостей

| Слой | Может импортировать из `clipflow.*` |
| --- | --- |
| `domain` | только `domain` |
| `application` | `domain`, `application` |
| `providers` | `domain`, `application`, `providers` |
| `infrastructure` | всё, кроме `ui` |
| `ui` | `domain`, `application`, `ui`, `version` |

Исключения — точки сборки приложения, им разрешено всё: `ui/bootstrap.py` (корень сборки главного процесса), `ui/self_test.py` (самопроверка упакованной сборки), `infrastructure/auth_process/__main__.py` и `infrastructure/auth_process/window.py` (отдельный GUI-процесс входа; ему нужны тема, переводчик и иконка главного окна). Пакет `auth_process` не переносится: его путь записан в `scripts/package_config.py` (hiddenimports) и `scripts/package_smoke.py`, а проверить сборку сейчас нельзя.

Новый тест `tests/unit/test_layers.py` разбирает импорты (`ast`, включая импорты внутри функций и под `TYPE_CHECKING`) всех модулей `src/clipflow` и падает на нарушении таблицы с именем модуля и запрещённого импорта.

## Срез 0 — храповик правил

В `[tool.ruff.lint]` `select` добавляются `C90` и `BLE`, `[tool.ruff.lint.mccabe] max-complexity = 10`. На каждом из 43 текущих мест — `# noqa: C901  # подпроект 3` или `# noqa: BLE001  # подпроект 3`. Код не меняется. С этого коммита `check.py` не пропустит новые нарушения.

## Срез 1 — ошибки и границы

- `application/errors.py`: `class JobRuleError(ValueError)` с атрибутом `code` и понятным сообщением. Планировщик и `SubmissionService` бросают его вместо `ValueError` с текстом. Коды:

  | Текущий текст | Код |
  | --- | --- |
  | Scheduler is shut down | `scheduler_closed` |
  | Job cannot be started | `job_not_startable` |
  | Job source must be provided again | `source_required` |
  | Job cannot be resumed | `job_not_resumable` |
  | Cooldown has not expired | `cooldown_active` |
  | Only terminal jobs can be retried | `job_not_retryable` |
  | Job is not waiting for this source | `source_not_expected` |
  | Source changed; add it as a new job | `source_changed` |
  | Job is not waiting for a nonempty selection / for selection | `selection_not_expected` |
  | Unsupported submission mode | `invalid_mode` |
  | This job is already queued or active | `job_not_repeatable` |

  `WorkbenchPresenter._command` берёт `getattr(error, 'code', 'action_failed')` без разбора текста. Показанный текст не меняется: у кодов без своего текста окно и сейчас показывает `error.generic` (ключа `error.action_failed` в каталоге нет); меняется только подсказка строки ошибки — точный код вместо `action_failed`. Поэтому ни один новый код, кроме `source_changed` и `cooldown_active`, не должен совпадать с ключом `error.<код>` каталога (например, не `already_queued` — иначе повтор активного задания показал бы «уже в очереди»); это закрепляет тест. Тесты, ожидающие `ValueError`, продолжают проходить (наследник).
- `domain/failures.py`: `FAILURE_GROUPS` (код → группа) и `AUTH_SETTINGS_CODES` переезжают из `ui/job_status.py`; функция `failure_group(code: str) -> str` (неизвестный → `'internal'`). `ui/job_status.py` хранит только тексты групп и форматирование. Сканирующий тест кодов из подпроекта 2 сверяет исходники с `domain/failures.py`.
- `MediaItem` переезжает в `domain/models.py`; `providers/base.py` реэкспортирует его (`from clipflow.domain.models import MediaItem`), импорты провайдеров и тестов не меняются. `domain/paths.py` импортирует из домена.
- `ui/history.py` → `application/history.py` (`HistoryError`, `deletion_paths`, `result_status`) плюс чистая функция `removable_targets(jobs, pending: set[str]) -> set[str]` — алгоритм «оставить предков незавершённых детей» из `_flush_clear`. Старый модуль удаляется, импорты обновляются.
- `BROWSERS` переезжает в `domain/models.py`; `infrastructure/auth.py` и `ui/accounts.py` берут его оттуда.
- `tests/unit/test_layers.py` (см. выше).

## Срез 2 — MediaPipeline

Публичное API прежнее: `MediaPipeline(*, ffmpeg, ffprobe, node)`, `save(item, request, context)`, и тестам доступны `MediaPipeline._run`/`_telemetry` (тестовые ссылки сохраняются как атрибуты класса, делегирующие в новые модули).

- `providers/media_plan.py`: `@dataclass(frozen=True) MediaPlan(target, work, tag, post)` и чистая `plan_media(request, item) -> MediaPlan` (идентичность поста Instagram, `output_path`, тег `clipflow:<id>` для YouTube, временное имя).
- `providers/processes.py`: запуск внешнего процесса с отменой и остановка дерева процессов (`run_process`, `stop_process_tree`).
- `providers/conversion.py`: ffprobe/проверка результата/конвертация ffmpeg/подпись (`probe_media`, `verify_media`, `convert_media`, `write_caption`).
- `providers/publishing.py`: публикация без перезаписи через hard link, поиск готового файла по тегу, нумерация « (n)».
- `MediaPipeline.save` — сценарий: план → готовый файл (проверить) или загрузка фото/видео (`_download_photo`, `_download_video`) → подпись → `FilesSaved`. Обработка исключений (коды `invalid_path`, `write_failed`, `download_failed`) остаётся в `save`.

## Срез 3 — WorkbenchPresenter

`WorkbenchPresenter` в `ui/presenter.py` остаётся фасадом: те же публичные методы, сигналы, атрибуты `model`, `settings`, `executor`, `scheduler`, `repository`, `auth_gateway`, `title_interval_ms`, `_reload_jobs`, `_tick`, `_poll_auth`. Работа передаётся помощникам:

- `application/probe_cache.py`: `ProbeCache(ttl=120.0, limit=100, clock=time.monotonic)` с `key_for(request)`, `get(key)`, `put(key, heights)`, `clear()`. Без Qt.
- `ui/presenter_clearing.py`: очередь очистки и удаление файлов (`clear_all`, `_flush_clear`, `delete_files`, `remove_jobs`, `clear_history`) поверх `application/history.py`.
- `ui/presenter_accounts.py`: шлюз аккаунтов, опрос раз в секунду, вход, выход (с паузой активных заданий профиля), настройка и импорт GetCourse.
- `ui/presenter_titles.py`: фоновая подгрузка названий (одна за раз, интервал `title_interval_ms`, одна попытка на задание за сессию).
- Настройки (`update_preset`, `update_folder`, `set_auto_start`, `update_preferences`, `_save_settings`) остаются в фасаде — это короткие методы.
- `toggle_job` — словарь «состояние → обработчик» вместо цепочки `if`.

Помощники получают фасад или нужные зависимости в конструкторе и сообщают ошибки через тот же `_command`/`error_raised`.

## Срез 4 — MainWindow

- `ui/sidebar.py`: `Sidebar(QFrame)` — логотип, кнопки навигации, «Аккаунты»/«Настройки», подпись. Сигналы `navigate(service, history, key)` и `section(name)`.
- `ui/queue_panel.py`: `QueuePanel(QWidget)` — счётчик, кнопки очереди и их перенос (`_arrange_queue_controls`), вкладки статуса, список с делегатом и фильтром, пустое состояние, счётчики вкладок.
- `ui/window_menus.py`: построение строки меню (`_menus`, правка, язык, тема, «Загрузки»).
- `ui/window_dialogs.py`: подтверждения очистки и удаления, выбор элементов, ввод источника, контекстное меню истории, пакетное добавление.
- `MainWindow` собирает части, связывает сигналы и пробрасывает атрибуты, на которые опираются тесты: `presenter`, `composer`, `url_input`, `add_button`, `folder_input`, `auto_start`, `queue_view`, `proxy`, `start_button`, `cancel_queue_button`, `clear_all_button`, `batch_button`, `nav_buttons`, `status_buttons`, `accounts_button`, `settings_button`, `accounts_page`, `settings_page`, `language_actions`, `theme_actions`, `downloads_menu`, `error_label`, `composer_host`, `main_page`, `theme`, `tr`, `_dialogs`, `_navigate`, `_confirm_delete`, `_select_dialog`, `_source_dialog`, `_history_menu`, `_accent`.

## Срез 5 — остальные сложные функции

Каждая доводится до сложности ≤10 выделением шагов в именованные функции или таблицы: `Scheduler.handle` (таблица обработчиков по типу события), `SubmissionService.preview`, `domain/paths.output_path`, `domain/urls.parse_url`, `NativeAuthGateway.options_for`, `auth_process.__main__.main`, `AppSettings._migrate`, `access.run_pp`, `GetCourseProvider._session`, `InstagramProfileProvider.execute` и `pages`, `YouTubeProvider.probe`, `Composer.__init__`, `QueueDelegate.paint`, `self_test.main`.

Сюда же — тела `run()` воркеров исполнителя: `infrastructure/work.py` с публичными `run_download(provider, request, context) -> terminal`, `run_probe(...) -> (heights, error)`, `run_title(...) -> title`; классы `QThread` в `executor.py` только вызывают их. `test_executor_workers.py` переходит на эти функции.

## Срез 6 — широкие except

Для каждого из 25 мест одно из двух:

- сужение до известных исключений, если они перечислимы (проверяется тестом, что неожиданное исключение не глотается там, где это важно);
- `# noqa: BLE001  # <причина>` с настоящей причиной: граница потока-воркера (сбой превращается в код задания), защита Qt-колбэка (исключение в слоте не должно ронять цикл событий), сбой сторонней библиотеки с секретами в тексте (наружу только безопасный код), самопроверка сборки.

В конце `tests/unit/test_layers.py` (или соседний тест) проверяет, что в `src` не осталось пометок `# подпроект 3`.

## Тесты и проверка

- Новое (`JobRuleError`, `failure_group`, `removable_targets`, `ProbeCache`, `plan_media`, функции `work.py`, тест слоёв) — сначала тест, наблюдаемое падение, затем код.
- Перенос без изменения поведения проверяется существующими тестами; тестовые ожидания не ослабляются. Правка теста — только по существу (новое место импорта, публичная функция вместо приватного класса), с объяснением в коммите.
- После каждого среза — полный `scripts/check.py` на Mac (ruff, тесты, пороги: ядро ≥95% строк и ≥90% ветвей, всё ≥85%). Если `test_batch_shortcut_ctrl_command_n` падает при заблокированном экране, это фиксируется как среда, а не регрессия.
- В конце — push в `dev`, зелёный CI Windows и macOS на точном SHA, финальное ревью opus high.

## Риски

- Запас runtime-покрытия мал (85,39% при пороге 85%). Новые модули (`work.py`, `media_plan.py`, `probe_cache.py`) покрываются прямыми тестами, что должно поднять запас; если срез опускает покрытие ниже порога, срез не закрыт.
- Разбор `MainWindow` затрагивает порядок создания виджетов и стилей; тесты геометрии (перенос панели, высота кнопок, ширина окна 880 px) — главный страховочный набор. Windows-метрики шрифтов проверяются CI.
- Перенос кода между модулями ломает `git blame`; каждый перенос — отдельный коммит без смысловых правок, где это возможно.

## Вне рамок

Слой use cases, презентер без Qt, перестройка пакетов, перенос `auth_process`, изменение текстов и поведения, ревизия тестов (подпроект 4), сборки.
