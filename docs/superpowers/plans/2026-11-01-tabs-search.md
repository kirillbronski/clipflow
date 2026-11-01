# Вкладки типа, поиск и сортировка — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Одна строка над списком как в 4K: вкладки типа слева, справа статус списком с числами, «N элементов», поиск и сортировка; сортировка меняет только показ.

**Architecture:** Чистые правила (тип задания, нормализация текста, естественный ключ) — в `application/queue_view.py`; `QueueFilter` получает тип, запрос и сортировку (`lessThan`); новый виджет `QueueToolbar` заменяет вкладки статуса в `QueuePanel`.

**Tech Stack:** Python 3.12, PySide6, pytest + pytest-qt, ruff 0.17.3.

**Spec:** `docs/superpowers/specs/2026-11-01-tabs-search-design.md`

## Global Constraints

- Ключи типа: `'all' | 'video' | 'audio' | 'photo' | 'playlists'`; ключи сортировки: `'added' | 'title' | 'size' | 'duration'`, плюс флаг `descending`.
- «Аудио» — `options.format == 'mp3'`; «Фото» — `details.photo` или Instagram с `media_filter == 'photo'`; «Видео» — остальные не-группы; «Плейлисты» — строки групп (`model.is_group_row`).
- Группа в «Видео/Аудио/Фото» видна, если хотя бы один её трек этого типа (как статус); на экране группы тип фильтрует треки, «Плейлисты» там показывает все треки.
- Поиск: подстрока после `normalize` (casefold, «ё»→«е», strip) в названии строки (`TitleRole`), `details.author`, `link.canonical_url`; группа видна при совпадении её или любого трека.
- Сортировка: неизвестные значения в конце при любом направлении; при равенстве — порядок очереди; группа — сумма размеров/длительностей треков; порядок загрузки (`repository.list()`, запуск очереди) не меняется.
- Тексты (ru / en): вкладки «Все» «Видео» «Аудио» «Фото» «Плейлисты» / «All» «Video» «Audio» «Photos» «Playlists»; элементы «1 элемент / 2 элемента / 5 элементов» / «1 item / 5 items»; поле — «Поиск по названию, автору и ссылке» / «Search by title, author and link»; сортировка «По дате добавления» «По названию» «По размеру» «По длительности» «По убыванию» «Порядок загрузки не меняется» / «Date added» «Title» «Size» «Duration» «Descending» «Download order does not change»; пусто — «Ничего не найдено» / «Nothing found».
- ⌘F / Ctrl+F — `QKeySequence.StandardKey.Find`; Esc в поле — очистить и свернуть.
- Скорость: 2000 заданий — смена вкладки, символ поиска, смена сортировки ≤ 0,5 с каждая и без чтения базы.
- Покрытие: ядро ≥95 % строк / ≥90 % ветвлений, программа ≥90 %.

## Review Focus

1. Поиск по русскому тексту с «Ё» и разным регистром («ЁЛКА» находит «ёлка» и «елка») — тест `test_search_ignores_case_and_yo` (Task 2).
2. Задание без сведений (старая очередь) при сортировке по размеру и длительности уходит в конец в обе стороны, а не ломает сравнение — тест `test_unknown_values_sort_last_both_ways` (Task 3).
3. Новое задание добавилось, пока включены сортировка и поиск: оно встаёт на своё место и проходит через фильтр без перезапуска — тест `test_new_jobs_respect_sort_and_search` (Task 3).
4. Смена площадки в боковой панели сохраняет тип, статус, поиск и сортировку — тест `test_sidebar_keeps_filters` (Task 5).
5. Выделенная строка скрылась фильтром — меню и Enter не действуют на невидимую строку — тест `test_hidden_selection_is_dropped` (Task 5).

---

### Task 1: Чистые правила показа

**Files:**
- Create: `src/clipflow/application/queue_view.py`
- Test: `tests/unit/test_queue_view.py`

**Interfaces:**
- Produces: `job_kind(job: Job) -> str` ('video' | 'audio' | 'photo'); `normalize(text: str | None) -> str`; `natural_key(text: str | None) -> tuple` — части текста после `normalize`, числа как `(0, int)`, остальное как `(1, str)`.

- [ ] **Step 1: Тесты**

```python
def test_kinds():
    assert job_kind(job('https://youtu.be/a', fmt='mp3')) == 'audio'
    assert job_kind(job('https://music.youtube.com/watch?v=a')) == 'audio'  # forced MP3
    assert (
        job_kind(job('https://www.instagram.com/p/A/', details=MediaDetails(photo=True))) == 'photo'
    )
    assert job_kind(job('https://www.instagram.com/p/A/', media_filter='photo')) == 'photo'
    assert job_kind(job('https://youtu.be/a')) == 'video'


def test_normalize():
    assert normalize('  ЁЛКА ') == 'елка'
    assert normalize(None) == ''


def test_natural_key_orders_numbers():
    titles = ['Урок 10', 'урок 2', 'Урок 1']
    assert sorted(titles, key=natural_key) == ['Урок 1', 'урок 2', 'Урок 10']
```

- [ ] **Step 2:** `pytest tests/unit/test_queue_view.py -q` → FAIL (нет модуля).
- [ ] **Step 3:** Реализовать (`re.split(r'(\d+)', ...)`).
- [ ] **Step 4:** тот же запуск → passed; `pytest tests/unit/test_layers.py -q` → passed.
- [ ] **Step 5:** Commit `feat: queue view rules for kind, search text and natural order`.

### Task 2: Фильтр по типу и поиску

**Files:**
- Modify: `src/clipflow/ui/queue_model.py` (`QueueFilter`)
- Test: `tests/ui/test_queue_filter.py`

**Interfaces:**
- Consumes: Task 1.
- Produces: `QueueFilter.kind: str`, `QueueFilter.query: str` (нормализованный); `show_kind(kind: str) -> None` (иначе `ValueError('invalid_kind')`); `show_query(text: str) -> None`; `count(status)` учитывает тип, запрос, площадку, историю и экран группы.

- [ ] **Step 1: Тесты** (`JobListModel` + `QueueFilter` напрямую, как `test_queue_groups.py`)
  - `test_kind_tabs_on_a_mixed_queue` — одиночные видео, MP3, фото и плейлист из 1 MP3-трека и 1 видео: `video` → видео + плейлист; `audio` → MP3 + плейлист; `photo` → фото; `playlists` → только плейлист.
  - `test_kind_inside_a_group` — экран группы: `audio` → только MP3-трек; `playlists` → оба трека.
  - `test_search_by_title_author_and_link`.
  - `test_search_ignores_case_and_yo`.
  - `test_search_finds_a_group_by_its_track`.
  - `test_counts_follow_kind_and_search` — `count('all')`, `count('completed')` при `audio` и запросе.
- [ ] **Step 2:** `pytest tests/ui/test_queue_filter.py -q` → FAIL.
- [ ] **Step 3:** Реализовать: в `_matches` добавить проверки типа и запроса для одиночного задания; для строки группы — `kind == 'playlists'` или правило «по содержимому», запрос — сама группа или любой трек; на экране группы `playlists` не фильтрует. Заголовок строки для поиска — `model.data(index, TitleRole)`.
- [ ] **Step 4:** `pytest tests/ui/test_queue_filter.py tests/ui/test_queue_groups.py -q` → passed.
- [ ] **Step 5:** Commit `feat: filter the queue by kind and search`.

### Task 3: Сортировка

**Files:**
- Modify: `src/clipflow/ui/queue_model.py` (`QueueFilter.lessThan`, `sort_by`; `JobListModel.DurationRole = JobIdRole + 10` — длительность задания или сумма у группы; `SizeRole` у группы — сумма размеров треков: реальный или ожидаемый)
- Test: `tests/ui/test_queue_filter.py`

**Interfaces:**
- Produces: `QueueFilter.sort_key: str`, `QueueFilter.descending: bool`; `sort_by(key: str, descending: bool = False) -> None` (иначе `ValueError('invalid_sort')`); `'added'` — порядок строк источника.

- [ ] **Step 1: Тесты**
  - `test_sort_by_each_key_both_ways` — названия «Урок 10 / Урок 2 / Урок 1», разные размеры и длительности; проверка порядка `proxy.index(r,0).data(JobIdRole)`.
  - `test_unknown_values_sort_last_both_ways`.
  - `test_ties_keep_queue_order`.
  - `test_group_sorts_by_its_totals`.
  - `test_sorting_does_not_change_download_order` — после `sort_by('title', True)` `repository.list()` и первое запускаемое задание прежние (через окно и `start_queue`).
  - `test_new_jobs_respect_sort_and_search`.
- [ ] **Step 2:** запуск → новые FAIL.
- [ ] **Step 3:** Реализовать: `sort(0, Qt.SortOrder.AscendingOrder)` вызывается один раз (`setDynamicSortFilter(True)`); `lessThan` строит ключ `(unknown, value, source_row)` и сам учитывает `descending`, чтобы неизвестные оставались в конце; `'added'` — `source_row`.
- [ ] **Step 4:** `pytest tests/ui -q` → passed.
- [ ] **Step 5:** Commit `feat: sort the queue view`.

### Task 4: Панель над списком

**Files:**
- Create: `src/clipflow/ui/queue_toolbar.py`
- Modify: `src/clipflow/ui/i18n.py`
- Test: `tests/ui/test_queue_toolbar.py`

**Interfaces:**
- Produces: `QueueToolbar(translator, parent=None)`; сигналы `kind_changed(str)`, `status_changed(str)`, `query_changed(str)`, `sort_changed(str, bool)`; атрибуты `kind_buttons: dict[str, QPushButton]` (objectName `'statusTab'`), `status_button: QPushButton` (меню `status_menu` с действиями `status_actions: dict[str, QAction]`), `items_label: QLabel`, `search_button`, `search_field: QLineEdit`, `sort_button` (меню `sort_menu`, `sort_actions: dict[str, QAction]`, `descending_action`); методы `set_counts(counts: dict[str, int])` (тексты «Все 12» и т. п., кнопка показывает выбранный), `set_visible_count(count: int)`, `open_search()`, `close_search()`.
- Ключи i18n: `kind.all/video/audio/photo/playlists`, `items_one/few/many`, `search_hint`, `sort.added/title/size/duration/descending/note`, `nothing_found`.

- [ ] **Step 1: Тесты**
  - `test_kind_tabs_emit_and_check_one`;
  - `test_status_menu_shows_counts_and_emits`;
  - `test_items_label_plural` (1, 2, 5, 21 — ru; 1, 5 — en);
  - `test_search_opens_filters_and_escape_clears` (`open_search` → поле видно и в фокусе; ввод «ёлка» → `query_changed('ёлка')`; Esc → пусто, свёрнуто, `query_changed('')`);
  - `test_search_with_text_stays_open_on_focus_loss`;
  - `test_sort_menu_emits_key_and_direction` (галочка у выбранного; «По убыванию» — отдельная галочка; подсказка — выключенное действие);
  - `test_sort_and_search_buttons_highlight_when_active` (свойство `active` и перерисовка стиля).
- [ ] **Step 2:** `pytest tests/ui/test_queue_toolbar.py -q` → FAIL.
- [ ] **Step 3:** Реализовать; значки кнопок — текст «🔍» и «⇅»; подсветка — `setProperty('active', True)` и правило темы `QPushButton#statusTab[active="true"]`/`QToolButton[active="true"]` в `themes.py`.
- [ ] **Step 4:** тот же запуск → passed; `pytest tests/ui/test_texts.py -q` → passed.
- [ ] **Step 5:** Commit `feat: queue toolbar with kind tabs, status, search and sorting`.

### Task 5: Панель в окне

**Files:**
- Modify: `src/clipflow/ui/queue_panel.py` (`_status_tabs` → `QueueToolbar`; `filter_status`; `update_counts`; надпись «Ничего не найдено»; снятие выделения со скрытых строк), `src/clipflow/ui/window.py` (атрибуты `status_tabs`/`status_buttons` → `queue_toolbar`; ⌘F), `src/clipflow/ui/window_menus.py` (если сочетание удобнее как действие меню «Правка → Найти»)
- Test: `tests/ui/test_queue_search_window.py`; Modify: `tests/ui/test_design_parity.py:37-56`, `tests/ui/test_workbench.py:512`, `tests/ui/test_queue_groups.py:245-248`

**Interfaces:**
- Consumes: Tasks 2–4.
- Produces: `window.queue_toolbar`; `QueuePanel.filter_status(status)` сохраняется и ведёт через меню статуса; `window.status_buttons` убирается.

- [ ] **Step 1: Тесты**
  - `test_toolbar_drives_the_list` (тип, статус, поиск, сортировка через виджеты меняют строки списка и «N элементов»);
  - `test_find_shortcut_focuses_search` (⌘F/Ctrl+F через `QKeySequence.StandardKey.Find`);
  - `test_nothing_found_message`;
  - `test_sidebar_keeps_filters`;
  - `test_hidden_selection_is_dropped`;
  - `test_group_screen_uses_the_same_filters` (открыть плейлист — тип/поиск/сортировка действуют на треки, «← Назад» возвращает);
  - `test_toolbar_fits_narrow_window` (минимальная ширина окна — нет горизонтальной прокрутки, правые элементы не перекрывают вкладки; `items_label` скрыт первым);
  - `test_filters_are_fast_on_2000_jobs` (2000 заданий; смена вкладки, ввод символа, смена сортировки — каждая ≤ 0,5 с; `repository.list` подменён счётчиком — 0 вызовов).
  Правки старых тестов: `window.status_buttons[s].click()` → `window.queue_toolbar.status_actions[s].trigger()`; в `test_workbench` — `window.queue_toolbar is panel.queue_toolbar`; в `test_queue_groups` — текст `panel.queue_toolbar.status_actions['all'].text()`.
- [ ] **Step 2:** `pytest tests/ui/test_queue_search_window.py -q` → FAIL.
- [ ] **Step 3:** Реализовать.
- [ ] **Step 4:** `pytest tests/ui -q` → passed.
- [ ] **Step 5:** Commit `feat: kind tabs, search and sorting above the queue`.

### Task 6: Документы и полная проверка

**Files:**
- Modify: `README.md`, `docs/CHANGELOG.md` («## Следующая версия»), `docs/PROJECT-MEMORY.md`

- [ ] **Step 1:** Дописать документы: вкладки типа, статус списком, поиск (⌘F), сортировка, «порядок загрузки не меняется».
- [ ] **Step 2:** `rm -rf .ruff_cache && .venv/bin/python scripts/check.py` → «All offline Qt checks and coverage gates passed.»
- [ ] **Step 3:** Живой прогон из исходников со снимком окна: очередь с видео, MP3 и плейлистом; вкладки, поиск «ted», сортировка по размеру.
- [ ] **Step 4:** Commit `docs: tabs, search and sorting`.
