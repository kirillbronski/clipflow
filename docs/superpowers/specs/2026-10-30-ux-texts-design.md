# Подпроект 2: UX и тексты

Статус: дизайн подтверждён владельцем 30 октября 2026 по секциям; спецификация ждёт проверки владельцем.

## Контекст

Чистка проекта из четырёх подпроектов; подпроект 1 (ruff) закрыт. Сборок Windows и Mac не делать до конца всех четырёх. Ревью UX нашло: причина ошибки задания не видна (около 37 кодов сводятся к «Не удалось скачать»); мета-строка задания неточна для MP3 и фото; три похожие кнопки очереди и два пункта меню путают; символы «▷ ↓ +» вписаны в текст кнопок; дубли и устаревшие тексты; технический жаргон в окне входа; 8 неиспользуемых ключей.

## Решения владельца

- Причина ошибки показывается **вместо мета-строки** задания; справа остаётся «Не удалось скачать»; полный текст и код — во всплывающей подсказке.
- Кнопки: «Скачать всё», «Остановить всё», «Очистить…»; меню: «Убрать незавершённые», «Убрать завершённые».
- Символы в кнопках становятся **иконками**, текст кнопок — без символов.
- Секции 3 (тексты) и 4 (код и тесты) приняты как показаны.

## 1. Строка задания

### Причина ошибки

Для `state == FAILED` вторая строка — `error_text(...)`, цвет — как у статуса ошибки; подсказка строки (`ToolTipRole`) — тот же текст, перевод строки, `Код: <код>`. Для остальных состояний вторая строка — мета-строка (ниже), подсказка — название, как сейчас.

Группы (RU / EN):

| Группа | Коды | RU | EN |
|---|---|---|---|
| signin | `auth_required`, `auth_unavailable`, `instagram_access_required`, `getcourse_auth_failed` | Нужен вход в {service}. Откройте «Аккаунты». | Sign-in to {service} is required. Open Accounts. |
| access | `unavailable_media`, `instagram_unavailable_media`, `getcourse_access_denied`, `getcourse_no_media` | Материал недоступен: удалён, закрыт или нет доступа. | Item unavailable: removed, private or no access. |
| network | `download_failed`, `incomplete_download`, `probe_failed`, `getcourse_probe_failed`, `instagram_profile_failed`, `instagram_profile_incomplete` | Не удалось скачать. Проверьте интернет и повторите. | Download failed. Check your connection and try again. |
| save | `write_failed`, `invalid_path` | Не удалось сохранить файл. Проверьте папку и свободное место. | Could not save the file. Check the folder and free space. |
| processing | `processing_failed`, `invalid_media`, `missing_output` | Файл получен, но не обработан. Повторите загрузку. | File received but not processed. Download it again. |
| tool | `tool_missing` | Не найден FFmpeg. Переустановите ClipFlow. | FFmpeg not found. Reinstall ClipFlow. |
| changed | `getcourse_selection_changed`, `instagram_selection_changed` | Содержимое по ссылке изменилось. Добавьте её заново. | The link content has changed. Add it again. |
| empty | `no_output`, `instagram_no_matching_media` | По ссылке нет подходящих материалов. | No matching items at this link. |
| internal | `worker_failed`, `worker_start_failed`, `invalid_request`, `invalid_provider_event`, `instagram_rate_policy_required`, `instagram_post_required`, `instagram_profile_required`, `instagram_incomplete_metadata`, `instagram_invalid_metadata`, любой неизвестный код | Внутренняя ошибка ClipFlow. Повторите; если не помогло — сообщите код. | Internal ClipFlow error. Try again; if it persists, report the code. |

Коды настроек входа используют существующие тексты `error.<код>`: `auth_invalid_settings`, `auth_invalid_school`, `auth_scope_mismatch`, `auth_storage_failed`, `auth_launch_failed`.

`{service}` — отображаемое имя площадки задания (YouTube, Instagram, GetCourse).

Составной код `instagram_item_failed:<NNN>:<причина>` → «Элемент {number} не скачан: » / «Item {number} failed: » + текст группы причины; `{number}` — число без ведущих нулей.

Подсказка: «Код: {code}» / «Code: {code}» — исходная строка `job.error` целиком.

### Мета-строка

`<Площадка>  ·  <формат>  ·  <качество>` (разделитель как сейчас):

- `format == 'mp3'` → `MP3  ·  320 кбит/с` / `320 kbps`;
- видео без лимита → `MP4  ·  Лучшее качество`; с лимитом → `MP4  ·  до 720p` (существующий `quality_cap`);
- Instagram, `media_filter == 'photo'` → `Фото  ·  Исходный формат` (существующие `photo`, `original_format`);
- Instagram, `media_filter == 'all'` → `Фото и видео  ·  <формат>` / `Photos and videos  ·  <format>`;
- Instagram, `media_filter == 'video'` → как видео.

## 2. Кнопки, меню, иконки

| Ключ | RU | EN | Иконка |
|---|---|---|---|
| `start_queue` | Скачать всё | Download all | ▷ |
| `cancel_queue` | Остановить всё | Stop all | — |
| `clear_all` | Очистить… | Clear… | — |
| `add_primary` | Добавить в очередь | Add to queue | ↓ |
| кнопка «Несколько ссылок» | использует `batch` (Несколько ссылок / Multiple links); ключ `batch_button` удалить | | + |
| `clear_queue` (меню) | Убрать незавершённые | Remove unfinished | — |
| `clear_history` (меню) | Убрать завершённые | Remove finished | — |
| новая подсказка обоих пунктов | Файлы на диске останутся | Files on disk are kept | — |

Поведение кнопок и пунктов меню не меняется. Ключ `add` (дубль) удалить: кнопка подтверждения в окне «Несколько ссылок» (`batch_dialog.py`) берёт текст `add_primary`, но без иконки — иконка только у кнопки composer.

Иконки — `QIcon`, нарисованный из того же символа цветом текста кнопки (основная кнопка — цвет `accent_text`), перерисовывается при смене темы; доступное имя кнопки — только слова.

## 3. Тексты

| Ключ | RU было → станет | EN было → станет |
|---|---|---|
| `sources_label` | «И С Т О Ч Н И К И» → «Источники»; заглавные и разрядка — шрифтом (`QFont.Capitalization.AllUppercase`, межбуквенный интервал) | «S O U R C E S» → «Sources» |
| `footer` | удалить вместе с виджетом подвала (дубль `local_note`; версия есть в заголовке окна и «О программе») | — |
| `youtube_hint` | → «Видео, музыка и плейлисты YouTube. Ссылки YouTube Music сохраняются в MP3.» | → «YouTube videos, music and playlists. YouTube Music links are saved as MP3.» |
| `getcourse_hint` | без изменений | → «Only materials you have access to are downloaded.» |
| `auto_start` | «Автозапуск» → «Скачивать сразу» | «Auto-start» → «Start immediately» |
| `description_beside` | без изменений | «Save description» → «Save description beside file» |
| `quality_pending` | → «Проверяем доступное качество… Добавить в очередь можно уже сейчас.» | → «Checking available quality… You can add to the queue now.» |
| `probe_cancelled` | → «Проверка остановлена, чтобы начать загрузку. Добавить в очередь можно уже сейчас.» | → «Quality check stopped to start a download. You can add to the queue now.» |
| `probe_unavailable` | → «Проверка качества сейчас недоступна. Добавить в очередь можно.» | → «Quality check is unavailable right now. You can still add to the queue.» |
| `auth_native_mode` / `auth_ipad51` / `auth_ipad87` | → «Обычный» / «Совместимость 1» / «Совместимость 2» | → «Standard» / «Compatibility 1» / «Compatibility 2» |
| `school_scope_note` | → «Доступ — только к школе из этой ссылки. Для «Сессии браузера» войдите в школу и закройте браузер.» | → «Access applies only to the school in this link. For a browser session, sign into the school and close the browser.» |
| новый `import_old_profile_hint` (подсказка кнопки импорта) | «Старый профиль импортируется только для выбранной школы.» | «An old profile is imported only for the selected school.» |

Удалить неиспользуемые ключи: `filter_all`, `filter_active`, `filter_completed`, `filter_failed`, `instagram_subtitle`, `youtube_subtitle`, `getcourse_subtitle`, `delete`.

Внутренние ключи режимов входа (`'Обычный Qt WebEngine'`, `'Chrome на iPad · 51'`, `'Chrome на iPad · 87'` в `USER_AGENTS` и сохранённый выбор) **не менять** — меняются только отображаемые тексты.

## 4. Код и тесты

- Новый модуль `src/clipflow/ui/job_status.py`: `ERROR_GROUPS: dict[str, str]` (код → группа), `error_text(code: str, service: Service, translator) -> str`, `error_tooltip(code: str, service: Service, translator) -> str`, `meta_text(job: Job, translator) -> str`. `queue_delegate.py` и `queue_model.py` (подсказка) только используют их.
- Тексты групп — ключи `job_error.<группа>`, `job_error.item`, `job_error.code`, `meta.mp3_quality`, `meta.photos_videos` в `ui/i18n.py`.
- Тесты:
  - каждый код из исходников (`MediaFailure('…')`, `WorkFailed('…')`, `'no_output'`, причина в `instagram_item_failed`) имеет группу в `ERROR_GROUPS` или текст `error.<код>`; новый код без текста ломает тест;
  - составной код карусели и неизвестный код;
  - `meta_text` для MP3, видео с лимитом и без, Instagram «фото», «всё», «видео»;
  - строка с ошибкой: вторая строка = причина, подсказка содержит код;
  - новые подписи кнопок и пунктов меню, подсказка «Файлы на диске останутся»;
  - у кнопок «Скачать всё», «Добавить в очередь», «Несколько ссылок» есть иконка, в тексте нет «▷», «↓», «+»;
  - подвала нет; подпись «Источники» без пробелов между буквами;
  - каталоги RU и EN имеют одинаковые ключи; в коде нет ссылок на удалённые ключи;
  - подписи режимов входа новые, данные (`currentData`) прежние.
- Существующие тесты, проверяющие старые тексты, обновляются по существу (новый текст), без ослабления проверок.
- Проверка: полный `scripts/check.py`, CI обеих ОС, итоговое ревью субагентом opus high. Версию не поднимать, сборок нет.

## Вне рамок

Поведение очереди и кнопок, макет окна (кроме удаления подвала), перенос кодов ошибок в домен (подпроект 3), ревизия тестов (подпроект 4).
