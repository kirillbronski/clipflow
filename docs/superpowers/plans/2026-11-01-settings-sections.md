# Настройки по разделам — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Страница настроек с разделами слева («Основные», «Авторизация», «О программе»), тумблерами с пояснениями и пунктом меню «Настройки…»; аккаунты переезжают внутрь настроек.

**Architecture:** Новый самоотрисовывающийся `ToggleSwitch`; `SettingsPage` становится контейнером «колонка разделов + `QStackedWidget`» с помощниками `add_choice / add_toggle / add_divider`; `AccountsPage` вкладывается разделом без изменений; окно и боковая панель теряют отдельный раздел «Аккаунты».

**Tech Stack:** Python 3.12, PySide6 Qt Widgets, pytest + pytest-qt, ruff 0.17.3 (100 символов, одинарные кавычки).

**Spec:** `docs/superpowers/specs/2026-11-01-settings-sections-design.md`

## Global Constraints

- Хранение не меняется: никаких новых полей в `AppSettings`, `settings-v2.json` прежний.
- Сохранение без кнопки «Сохранить»: тема и язык — `presenter.update_preferences(**{key: value})`, автозапуск — `presenter.set_auto_start(enabled)`.
- Все тексты через `i18n` (ru и en), смена языка без перезапуска; `test_every_key_family_is_complete` запрещает собирать ключ конкатенацией — ключи явные.
- Ключи разделов: `'general'`, `'accounts'`, `'about'`; первый показ за запуск — `'general'`.
- Тексты: заголовки «Основные» / «Авторизация» / «О программе»; тумблер «Скачивать сразу после добавления»; пояснение «Загрузка начинается, как только ссылка попала в очередь. Если выключено, нажмите «Скачать всё».»; пункт меню «Настройки…». en: «General» / «Sign-in» / «About»; «Start downloading as soon as added»; «Downloads begin as soon as a link joins the queue. When off, press “Download all”.»; «Settings…».
- Цвета только из токенов темы (`theme.tokens()`, запасной `PALETTES['dark']`), как в `QueueDelegate`.
- Покрытие: ядро ≥95 % строк / ≥90 % ветвлений, программа ≥90 % (`scripts/check.py`).

## Review Focus

1. Смена языка, пока открыты настройки: подписи разделов, заголовок, тумблер и пояснение переводятся сразу — тест `test_settings_follow_language_switch` (Task 2).
2. Отказ сохранения автозапуска (`set_auto_start` вернул False): тумблер возвращается к сохранённому значению, как галочка composer — тест `test_auto_start_toggle_reverts_when_save_fails` (Task 2).
3. Смена темы: тумблер перерисовывается новыми цветами, а не запомненной палитрой — тест `test_toggle_reads_theme_on_each_paint` (Task 1).
4. Уход в очередь и возврат: открывается последний раздел, заголовок окна «Настройки» — тест `test_settings_remember_last_section` (Task 3).
5. Узкое окно (компактная боковая панель, минимальная ширина): у страницы нет горизонтальной прокрутки, пояснение переносится — тест `test_settings_fit_narrow_window` (Task 3).

---

### Task 1: Тумблер `ToggleSwitch`

**Files:**
- Create: `src/clipflow/ui/toggle.py`
- Test: `tests/ui/test_toggle.py`

**Interfaces:**
- Produces: `ToggleSwitch(QAbstractButton)`, `__init__(self, parent=None, *, theme=None)`; checkable; `sizeHint() -> QSize(36, 20)`; цвета: включён — `accent`, выключен — `border`, ручка — `accent_text` / `text`; `Qt.FocusPolicy.StrongFocus`.

- [ ] **Step 1: Тесты**

```python
def test_click_toggles_once(qtbot):
    switch = ToggleSwitch(); qtbot.addWidget(switch); seen = []
    switch.toggled.connect(seen.append)
    qtbot.mouseClick(switch, Qt.MouseButton.LeftButton)
    assert switch.isChecked() and seen == [True]

def test_space_toggles(qtbot):
    switch = ToggleSwitch(); qtbot.addWidget(switch); switch.show(); switch.setFocus()
    qtbot.keyClick(switch, Qt.Key.Key_Space)
    assert switch.isChecked()

def test_size_is_fixed(qtbot):
    assert ToggleSwitch().sizeHint() == QSize(36, 20)

def test_toggle_reads_theme_on_each_paint(qtbot):
    # theme stub with mutable tokens(); grab() twice with checked=True, accent changed between
    # grabs → the centre-left pixel colour of the track differs and equals the new accent
```

- [ ] **Step 2:** `pytest tests/ui/test_toggle.py -q` → FAIL (`ModuleNotFoundError: clipflow.ui.toggle`).
- [ ] **Step 3:** Реализовать `ToggleSwitch`: `paintEvent` рисует скруглённую дорожку и ручку диаметром 16 у левого/правого края; токены берутся в каждом `paintEvent`.
- [ ] **Step 4:** `pytest tests/ui/test_toggle.py -q` → 4 passed.
- [ ] **Step 5:** Commit `feat: painted toggle switch for settings`.

### Task 2: Разделы страницы настроек

**Files:**
- Modify: `src/clipflow/ui/settings_page.py`, `src/clipflow/ui/i18n.py`, `src/clipflow/ui/window.py` (передать `theme` и вложить `accounts_page` позже — в этой задаче только `theme`)
- Test: `tests/ui/test_settings_page.py`; Modify: `tests/ui/test_accounts.py::test_settings_page_reuses_persistent_theme_and_language` (остаётся зелёным без правок — `language_box`, `theme_box`, `about_label` сохраняются)

**Interfaces:**
- Consumes: `ToggleSwitch` (Task 1).
- Produces:
  - `SettingsPage(presenter, translator, parent=None, *, theme=None, accounts=None)`; `accounts` — виджет раздела «Авторизация» (`None` → раздела нет).
  - `show_section(key: str) -> None`, `current_section -> str`, `section_buttons: dict[str, QPushButton]` (objectName `'nav'`, checkable, в `QButtonGroup`; «О программе» отделён растяжкой внизу колонки), `section_title: QLabel`.
  - Помощники раздела: `add_choice(page, label_key, items: list[tuple[str, str]], getter, setter) -> QComboBox` (items — `(текст-ключ или готовый текст, значение)`), `add_toggle(page, label_key, hint_key, getter, setter) -> ToggleSwitch`, `add_divider(page) -> QFrame`. `page` — `QWidget` раздела с `QVBoxLayout`. Все созданные элементы обновляются в `refresh()` из `getter()`; тексты привязаны через `self.tr`.
  - Атрибуты: `language_box`, `theme_box`, `auto_start_toggle`, `about_label`.
  - Ключи i18n: `settings_section.general`, `settings_section.accounts`, `settings_section.about`, `auto_start_setting`, `auto_start_hint`, `menu_preferences` (последний используется в Task 4). Значок у пункта: `⚙` / `◉` / `ⓘ`.

- [ ] **Step 1: Тесты**

```python
def test_sections_switch_pages(make_window):
    window, _ = make_window(); window.settings_button.click(); page = window.settings_page
    assert page.current_section == 'general' and page.section_title.text() == 'Основные'
    page.section_buttons['about'].click()
    assert page.current_section == 'about' and page.about_label.isVisible()
    assert not page.language_box.isVisible()

def test_auto_start_toggle_and_composer_stay_in_sync(make_window):
    window, _ = make_window(); window.settings_button.click(); page = window.settings_page
    page.auto_start_toggle.click()
    assert window.presenter.settings.auto_start and window.composer.auto_start.isChecked()
    window.composer.auto_start.click()
    assert not window.presenter.settings.auto_start and not page.auto_start_toggle.isChecked()

def test_auto_start_toggle_reverts_when_save_fails(make_window, monkeypatch):
    window, _ = make_window(); window.settings_button.click(); page = window.settings_page
    monkeypatch.setattr(window.presenter, 'set_auto_start', lambda enabled: False)
    page.auto_start_toggle.click()
    assert not page.auto_start_toggle.isChecked()

def test_settings_follow_language_switch(make_window):
    window, _ = make_window(); window.settings_button.click(); page = window.settings_page
    page.language_box.setCurrentIndex(page.language_box.findData('en'))
    assert page.section_buttons['general'].text().endswith('General')
    assert page.section_title.text() == 'General'
    # the hint label under the toggle reads the English hint

def test_hidden_sections_are_absent(make_window):
    window, _ = make_window()
    assert set(window.settings_page.section_buttons) == {'general', 'accounts', 'about'} - {'accounts'}
    # в этой задаче accounts ещё не передан; Task 3 меняет ожидание на все три
```

- [ ] **Step 2:** `pytest tests/ui/test_settings_page.py -q` → FAIL (нет `section_buttons`).
- [ ] **Step 3:** Переписать `SettingsPage`: слева колонка 200 px, справа заголовок (pixelSize 20) и `QStackedWidget` из `QScrollArea` (без горизонтальной прокрутки, `widgetResizable`). «Основные»: `add_choice` язык, `add_choice` тема, `add_divider`, `add_toggle` автозапуск (setter — `presenter.set_auto_start`; при `False` — `refresh()`). «О программе»: версия и описание как сейчас. `presenter.settings_changed` и `tr.changed` → `refresh()`. Пояснение — `QLabel` objectName `'muted'`, `wordWrap`. В `window.py` создавать `SettingsPage(presenter, self.tr, self, theme=self.theme)`.
- [ ] **Step 4:** `pytest tests/ui/test_settings_page.py tests/ui/test_accounts.py tests/ui/test_texts.py -q` → passed.
- [ ] **Step 5:** Commit `feat: settings page with sections and toggles`.

### Task 3: Аккаунты внутри настроек

**Files:**
- Modify: `src/clipflow/ui/window.py`, `src/clipflow/ui/sidebar.py`
- Test: `tests/ui/test_settings_page.py`; Modify: `tests/ui/test_accounts.py`, `tests/ui/test_texts.py:173`, `tests/ui/test_design_parity.py:30-37,146-153`, `tests/ui/test_workbench.py:516`

**Interfaces:**
- Consumes: `SettingsPage(..., accounts=...)`, `show_section` (Task 2).
- Produces: `window.accounts_page` — `AccountsPage`, вложенный в настройки; `window.open_settings(section: str | None = None)` — показывает настройки (`_show_section('settings')`) и, если задан, раздел. `Sidebar.accounts_button` и раздел `'accounts'` окна удалены; `Sidebar.select(nav_key=None, section=None)` проверяет только `settings_button`.

- [ ] **Step 1: Тесты**

```python
def test_accounts_live_in_settings(make_window):
    window, _ = make_window()
    assert not hasattr(window.sidebar, 'accounts_button')
    window.open_settings('accounts')
    assert window.settings_page.current_section == 'accounts'
    assert window.accounts_page.isVisible()
    assert set(window.settings_page.section_buttons) == {'general', 'accounts', 'about'}

def test_settings_remember_last_section(make_window):
    window, _ = make_window(); window.open_settings('about')
    window.nav_buttons[0].click(); window.settings_button.click()
    assert window.settings_page.current_section == 'about'
    assert window.heading.text() == 'Настройки'

def test_settings_fit_narrow_window(make_window, qtbot):
    window, _ = make_window(); window.resize(window.minimumWidth(), 600)
    window.open_settings('general')
    area = window.settings_page.findChildren(QScrollArea)[0]
    assert area.horizontalScrollBar().maximum() == 0
```

Правки старых тестов: `window.accounts_button.click()` → `window.open_settings('accounts')`; `test_accounts_and_settings_stay_at_bottom_of_sidebar` → `test_settings_stays_at_bottom_of_sidebar` (только `settings_button.y() > height*0.65`); параметр `section` в `test_batch_button_only_visible_in_download_sections` → только `'settings'`; в `test_workbench.py` убрать строку про `accounts_button`; удалить из `test_hidden_sections_are_absent` (Task 2) вычитание `'accounts'` и переименовать в `test_all_sections_present`.

- [ ] **Step 2:** `pytest tests/ui/test_settings_page.py -q` → FAIL (`open_settings` нет).
- [ ] **Step 3:** В `window.py` создать `AccountsPage` и передать в `SettingsPage(accounts=...)`; убрать его из `main`, из `_navigate` и `_show_section`; добавить `open_settings`. В `sidebar.py` убрать `accounts_button` и его строку в `select`.
- [ ] **Step 4:** `pytest tests/ui -q` → все passed.
- [ ] **Step 5:** Commit `feat: accounts become the sign-in section of settings`.

### Task 4: Пункт меню «Настройки…»

**Files:**
- Modify: `src/clipflow/ui/window_menus.py`
- Test: `tests/ui/test_settings_page.py`

**Interfaces:**
- Consumes: `window.open_settings()` (Task 3), ключ `menu_preferences` (Task 2).
- Produces: `window.preferences_action` — `QAction` в меню «Настройки», `menuRole() == QAction.MenuRole.PreferencesRole`, сочетания `QKeySequence.keyBindings(StandardKey.Preferences)` или, если список пуст (Windows), `QKeySequence('Ctrl+,')`; добавлен в `window.addAction`.

- [ ] **Step 1: Тест**

```python
def test_preferences_action_opens_settings(make_window):
    window, _ = make_window(); action = window.preferences_action
    assert action.menuRole() == QAction.MenuRole.PreferencesRole
    assert action.shortcuts()
    action.trigger()
    assert window.settings_page.isVisible()
    assert action.text() == 'Настройки…'
```

- [ ] **Step 2:** `pytest tests/ui/test_settings_page.py::test_preferences_action_opens_settings -q` → FAIL (нет атрибута).
- [ ] **Step 3:** Добавить действие первым пунктом меню «Настройки», перед подменю «Язык», с разделителем после; `triggered` → `window.open_settings()`.
- [ ] **Step 4:** Тот же тест → PASS; затем `.venv/bin/python scripts/check.py` → зелёный, пороги покрытия выполнены.
- [ ] **Step 5:** Обновить README (пункт про настройки по разделам), CHANGELOG («## Следующая версия» — дописать «настройки по разделам, аккаунты внутри настроек»), `docs/PROJECT-MEMORY.md` (раздел о настройках и правило: новая настройка — строка `add_toggle`/`add_choice` в подходящем разделе, новый раздел появляется с первой настройкой). Commit `feat: Settings… menu item` и `docs: settings sections`.
