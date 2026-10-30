# ClipFlow — текущая память проекта

Обновлено 30 октября 2026 года. Это указатель на состояние работы, не замена актуальному Git, AGENTS и результатам проверок.

## Чистка проекта, подпроект 2 — UX и тексты, 30 октября

Спецификация `docs/superpowers/specs/2026-10-30-ux-texts-design.md`, план `docs/superpowers/plans/2026-10-30-ux-texts.md`, выполнение inline. Коммиты: 790f695 `ui/job_status.py` (группы кодов ошибок → понятный текст, `error_tooltip` с кодом, `meta_text`; тест сверяет все коды `MediaFailure`/`WorkFailed` из исходников), 7d6b927 причина ошибки во второй строке задания цветом error и подсказка модели, 5d805ae кнопки «Скачать всё»/«Остановить всё»/«Очистить…», меню «Убрать незавершённые/завершённые» с подсказкой, `glyph_icon` в themes, 964eb69 тексты по таблице, удалён подвал, `AUTH_MODES` в `auth_process/sessions.py`, тесты каталога (`tests/ui/test_texts.py`).
Отступления от спецификации (записаны в ledger): ключи `filter_*` и `*_subtitle` не удалены — они строятся динамически (`'filter_' + status`, `service + '_subtitle'`); тест семейств ключей это ловит. Диалог подтверждения очистки использует новый `clear_all_confirm` («Очистить всё»), потому что `clear_all` стал «Очистить…».
Итоговое ревью opus high: Critical нет. Исправлено: пять реальных кодов, которых нет в таблице спецификации (`instagram_rate_limited`, `instagram_probe_failed` → network; `instagram_access_denied`, `getcourse_school_login_required` → signin; `getcourse_invalid_player` → access), показывали «Внутренняя ошибка» — тест теперь собирает коды также из `SchoolAccessError` и `_network_reason`; Instagram «только фото» с пресетом MP3 показывал «MP3» вместо «Фото · Исходный формат». Отложено в подпроект 4: тест иконок проверяет cacheKey, а не цвет пикселей; тест ссылок на ключи не видит ключи в кортежах; строка теста с кодом GetCourse и Service.YOUTUBE.
Поведение очереди не менялось; версия не поднималась; сборок нет. Скриншоты README не пересоздавались и показывают старые подписи кнопок.

## Чистка проекта, подпроект 1 — единый стиль (ruff), 30 октября

Владелец поручил полную чистку из четырёх подпроектов: 1) ruff и форматирование; 2) UX и тексты; 3) архитектура и разбор MainWindow/WorkbenchPresenter/MediaPipeline; 4) ревизия тестов. Сборок (Windows и Mac) не делать до конца всех четырёх. Ревью кода, UX и тестов перед стартом — в истории чата и спецификации подпроекта 1.
Подпроект 1 выполнен: спецификация `docs/superpowers/specs/2026-10-30-ruff-formatting-design.md`, план `docs/superpowers/plans/2026-10-30-ruff-formatting.md`. Коммиты: 6a9dca5 конфигурация (ruff 0.17.3, 100 символов, одинарные кавычки, E/W/F/I/B/UP/SIM; тесты игнорируют F401/F811 из-за импорта фикстур; i18n/themes игнорируют E501), 4cec26d механическое форматирование (AST всех файлов совпадает), b896574 тесты логики QThread-воркеров (coverage.py не трассирует QThread), d5fb6ff безопасные автоисправления и `.git-blame-ignore-revs`, d6634f6 перенос длинных строк (тексты и палитры сверены снимком), 6d74f1d остальные замечания, 0c06f6d проверка ruff в `scripts/check.py`.
Mac check: 507 PASS/6 skips, core 96.39/91.84, runtime 85.21 — запас по runtime мал (формат увеличил число строк в модулях дочерних процессов); учесть в подпроекте 4. Отложено в подпроект 3: C901 (18 сложных функций), BLE001 (25 широких except, часть намеренная).
Итоговое ревью opus high: Critical нет; исправлено — запуск `check.py` не из корня давал 0% покрытия (14f6b66, тест), записано подтверждение владельца и способ переноса старых локальных правок. CI 14f6b66: macOS success, Windows — нестабильный `test_blocking_provider_does_not_block_gui_timer` (лимит 1,5 с); по решению владельца разбирается в подпроекте 4.
Отложено в подпроект 4: этот тест и другие жёсткие таймауты/sleep; запас runtime-покрытия 0,21%; `F401` для всех тестов (перенести общие фикстуры в conftest.py); `packaging/*/ClipFlow.spec` вне ruff; тест check.py подменяет глобальный `subprocess.run`; `zip(strict=False)` → `itertools.pairwise`; нестабильный `test_batch_shortcut_ctrl_command_n` (фокус окна на Mac). В подпроект 3: `test_executor_workers` завязан на приватные классы воркеров.

## 2.0.3–2.0.4 — имена файлов и названия в очереди, 30 октября

2.0.3 (`c48d94b`): YouTube-файлы «Исполнитель - Название» без хеша, нумерация плейлиста только по галочке (по умолчанию выкл.), идентичность — тег comment `clipflow:<id>` (повтор переиспользует, другой трек → « (n)», публикация через hard link без перезаписи), подпись «MP3». CI Windows упал на новом тесте бюджета пути (корень `D:\`), исправлено в 2.0.4.
2.0.4 (`7bcd925`): метки при обнаружении (плейлист, урок, подпись поста), название плейлиста у родителя, фоновая подгрузка будущего имени YouTube через слот `ThreadExecutor.request_title` (не занимает слот загрузки, учитывается при закрытии/drain), `Job.title` и `DownloadRequest.label` в базе (старые записи читаются, ключи не меняются). Mac check 491 PASS/6 skips. Обе версии собраны, установлены на Mac и в Parallels, файлы в Drive. Отчёт: [releases/2.0.4-candidate-2026-10-30.md](releases/2.0.4-candidate-2026-10-30.md).
CI 7bcd925: Windows упал в native auth (`parent_close`, код 1); в Parallels тот же шаг 21/21 дважды. Повторный CI на 853b732 (тот же код + документация): Windows и macOS success — разовая нестабильность runner.

## 2.0.2 — MP3 и папка плейлиста, 30 октября

Владелец сообщил, что Music-плейлист не скачивается. Причина: probe-метаданные несли `requested_formats` выбора yt-dlp по умолчанию (видео+аудио); MediaPipeline передавал их второму YoutubeDL, и для MP3 загрузка шла по устаревшему набору → HTTP403 для любого MP3 с YouTube. Запись 2.0.1 о «403 без авторизации» была этим дефектом. Исправлено в `af721f6` (2.0.2), регрессия RED→GREEN, папка плейлиста — ровно `Название [ID]`.
Mac полный check 471 PASS/6 skips; CI Checks обеих ОС success. Сборки Mac (на Mac) и Windows (Parallels, Inno 6.7.3 поставлен в VM через winget по просьбе владельца) из af721f6, обе установлены, файлы в Мой диск/ClipFlow. Keychain для Mac 2.0.2 владелец подтвердил, главное окно 1180×832 проверено. Подробности: [releases/2.0.2-candidate-2026-10-30.md](releases/2.0.2-candidate-2026-10-30.md).
Сборка в Parallels требует `prlctl exec --current-user` (SYSTEM без рабочего стола роняет WebEngine smoke), mingit в PATH и `INNO_SETUP_COMPILER`. Основной Windows ПК остаётся на 2.0.0. main не менялся. После задачи — ПАУЗА.

## Доступ Keychain подтверждён — 30 октября

Владелец подтвердил системное разрешение для ClipFlow. Проверен фактический
запуск установленной /Applications/ClipFlow.app с существующим профилем:
NSRunningApplication finishedLaunching=True, одно видимое главное окно1180×832
(с системной рамкой), основной поток работает в Qt event loop вместо постоянного
ожидания SecItemCopyMatching. Новая переустановка или пересборка не требовалась.
Пункт ожидания доступа Keychain закрыт. Ни ключи, ни ACL агентом не сбрасывались.
Личный вход на площадки/закрытые материалы и foreground Command+N этим не
подтверждаются. main не менялся; после сохранения памяти — ПАУЗА.

## Итог предыдущей задачи — 30 октября

Все изменения кода/README/тестов отправлены в dev. Compiled source `bfd5726`;
verification head `d09a1dc` — GitHub checks Windows и macOS completed SUCCESS.
После сборки изменились только CI и ожидание settled layout в тесте; shipping
src/assets/packaging/runtime requirements/build scripts идентичны по git diff.
Пакеты не пересобирались без изменения продукта; provenance source SHA не подменён.
Итоговый [отчёт](releases/2.0.0-candidate-2026-10-30.md), SHA256 и verification.json
в согласованной папке владельца. DMG/EXE/APP ZIP/portable ZIP обновлены, обе установки
обновлены; Mac одна app, Windows Desktop shortcut responsive. Профили сохранены.

Ожидание системного разрешения Keychain закрыто подтверждением владельца и
проверкой normal-profile окна30 октября (см. актуальную запись выше). Native foreground Command+N и
личные/live acceptance остаются открыты. main не мержился. После сохранения
Agents/ClipFlow — ПАУЗА; не начинать новую функциональность без запроса владельца.

## Историческое уточнение тестовой проверки и Mac Keychain (до подтверждения владельца)

Полный Parallels прогон того же runtime bfd5726 дал457PASS/6skips и1FAIL:
RU toolbar test считывал width205 до отложенного Qt layout, тогда как glyph
требовал270px. Условие viewport>500 было истинным ещё до завершения resize.
Тест теперь ожидает ровно880px и те же прежние требования readable button width;
строгие assertions/timeout сохранены. Windows targeted6PASS и Mac native2PASS.
Runtime/assets/packaging по git diff идентичны clean compiled bfd5726; новая
проверка не требует ещё одной перекомпиляции неизменённого продукта. CI и тесты
имеют отдельный verification head; source artifact SHA всегда остаётся реальным.

Обе установки уже обновлены до bfd5726, обе frozen smoke PASS, Windows responsive
через Desktop shortcut. Mac normal profile ждёт системное разрешение Keychain:
SecItemCopyMatching на старом ключе профиля, не ошибка synthetic smoke. Никакие
ключи/ACL не сбрасывались. Старое ожидание чтения остановлено после backup и
проверки отсутствия active jobs; новая app установлена с сохранением профиля.
Владелец должен подтвердить системный доступ, чтобы normal GUI завершил запуск.
Pending native foreground Command+N/личные live gates не считать PASS.

## Проверка адаптации панели

Mac full458PASS/6 explicit skips; core97.26%/91.67%, runtime87.97%.
Native Cocoa bulk/layout47PASS. Windows offscreen targeted4PASS: исходный
failing caption case + RU/EN wide metrics + vertical fallback. Длинные labels
могут переноситься; кнопки не перекрываются, min880px и требования читаемости
не изменены. Требуются clean builds этого исходного среза и exact-SHA CI.

## Разбор Windows CI и адаптивная панель очереди

a25553e diagnostic подтвердил точную причину d422 Windows FAIL:
`test_mode_caption_yields_space_to_wide_control_metrics`. Три queue buttons
в одной строке вместе с count расширяли minimum width на Windows fallback fonts;
окно вместо880 становилось шире, composer оставлял Download caption видимым.
Новые RU/EN tests с wide metrics воспроизводят это RED→GREEN. Панель очереди
теперь переносит actions ниже счётчика, а при очень широких кнопках — вертикально;
её width hint не расширяет окно. Подсказки пустой очереди, subtitle и footer переносят длинный текст, а не
расширяют main content на Windows offscreen fallback fonts. После переноса
Win targeted4PASS, включая исходный failing caption case и RU/EN/narrow cases.
Min880×680 и все font/visibility assertions
сохранены, не ослаблять тест ради Windows CI. Новые final installers нужны,
установленные d422 пока не содержат эту адаптацию.

Внешний watchdog full check поднят360→600s (без пропусков/ослабления assertions):
реальные Mac CI full354s, Windows Parallels full474s уже превышали прежний запас.
Job budget20min; JUnit annotations сохраняются. a255 Mac CI PASS, Windows FAIL
по тому же конкретному layout test; main не мержить до нового exact-SHA GREEN.

## Установки и поставка — source d422da9

DMG/APP ZIP и Windows EXE/portable ZIP собраны из clean d422da9. Обе установки
обновлены, frozen UI/media/tools/auth checks PASS, Mac27 Launch Services из DMG
и /Applications PASS;582 Mac profile files и3 Windows profile files сохранены.
Windows Program Files/ClipFlow + public Desktop shortcut, окно responsive.
Артефакты/SHA256/verification.json в Мой диск/ClipFlow. У Mac одна .app;
собственные test app/build/archive копии очищены, production Keychain не тронут;
удалены236 synthetic test key entries. README Windows screenshot обновлён из
actual installed executable. Личные/live acceptance и notarization не закрыты.

ВАЖНО: GitHub d422da9 macOS15 PASS, Windows full offline step FAIL. Локальные
Parallels158PASS/1symlink skip и final bulk24PASS/1symlink skip не подменяют CI.
Без API log auth добавлен diagnostic workflow a25553e: JUnit full suite → public
error annotations. Его результат требуется разобрать. main не мержился.
Не называть source d422da9 fully accepted stable из-за этого открытого gate.

## Проверенный исходный срез — 30 октября

После final review fixes и bulk controls: полный Mac check455PASS/6 explicit
skips, core97.26% строк/91.67% ветвей, runtime87.92%; native Cocoa bulk/layout44PASS.
Отдельная foreground-проверка Command+N не принята: тестовое окно не получило
активацию (59 native PASS/1 FAIL в расширенном прогоне). Не скрывать этот gate.
Новые Windows native проверки и clean builds/install ещё выполняются; итоговый
source SHA/артефакты в последнем verification report и Agents snapshot.

## Последнее дополнение — массовая отмена и очистка

Владелец30 октября запросил видимые bulk buttons и optional physical deletion:
«Отменить очередь» останавливает все сервисы без удаления записей/файлов;
«Очистить всё» подтверждает очистку всех очередей/истории, с выключенной по
умолчанию галочкой удаления записанных файлов. Дождаться idle worker; путь
проверяется существующим deletion_paths, folders recursively не удаляются.
Deletion consent хранится по IDs: повторный диалог без галочки отзывает
удаление для своего снимка, прежний флаг не распространяется на новые jobs.
На IO/containment error сохраняются записи и показывается ошибка; destructive
операция не повторяется каждые500ms. Источник требований/проверки:
[план bulk queue](superpowers/plans/2026-10-30-bulk-queue.md).

## Предыдущий срез — 30 октября: установки, README и final review

Обе clean-сборки4ce2c97 установлены и проверены: Mac27 Launch Services из DMG
и /Applications, сохранены582 существовавших файла профиля; Windows11 ARM64
Parallels (x64 runtime under emulation), Inno в Program Files и ярлык Desktop,
installed frozen UI/media/tools/protected-auth smoke PASS. Точные4ce CI Windows
и macOS15 PASS. Установщики с проверенными SHA256 доставлены в Мой диск/ClipFlow.
Старые собственные Mac app/test build copies удалены, пользовательские файлы не тронуты.

Независимый whole-branch review нашёл2 дефекта: generic title collision и
потерянные child jobs при retry коллекции. Добавлены regression tests RED→GREEN:
имя YouTube/GetCourse сохраняет стабильный identity+quality suffix вне усечения;
Instagram01.mp4/01.txt не меняются. Discovery не дедуплицирует cancelled/failed
или completed child без существующих файлов, активные jobs/существующие outputs
сохраняют дедупликацию. Старые неидентифицированные медиа не удаляются и не
присваиваются новому видео. Требуется новый clean build/install этих исправлений;
4ce артефакты в Drive не считать содержащими последующие правки review.

README переработан: реальные Qt screenshots dark/light, Windows и полный IG
блок, режимы/папки/архитектура/разработка/пороги тестов. GitHub Releases пока нет.
Личные auth/закрытый GetCourse и live IGprofile10/50/all остаются непринятыми,
Mac подпись ad-hoc без notarization. Это не скрывать при дальнейшей передаче.

## Последнее уточнение: Instagram без внутреннего скролла и обе установки

Владелец просит более высокую панель Instagram: все раскрытые параметры,
включая папку, видны внутри блока без внутренней прокрутки. Если окно низкое,
скролл переносится на основную страницу; YouTube/GetCourse компактнее. Очередь
имеет минимум одну строку. Исправлены отличия высоты native Windows fonts:
не ослаблять min880×680/требования к видимости текста и очереди ради тестов.
Текущая проверка:437 offline PASS/6 skips, core97.24%/91.60%,runtime87.79%;
Mac Cocoa59 PASS (controls+auth), Windows Parallels38 native GUI/input PASS.
Windows полный435PASS/6skip на63b5248 занял474s в x64 эмуляции, пороги пройдены;
новые UI проверки проводились на текущем патче, финальные пакеты — из clean SHA.

Владелец дополнительно разрешил установить Windows EXE в Parallels и создать
ярлык на Desktop; до этой команды Windows personal installation не менялась.
На Mac удалить собственные временные .app/старые тестовые пакеты и регистрации,
оставить одну /Applications/ClipFlow.app; профиль/медиа/исходники не удалять.
После пакетов актуализировать красивый README с новой иконкой и настоящими
скриншотами нового интерфейса обеих платформ/тем; не обещать отсутствующие
публичные GitHub release assets. Все6 вариантов иконок сохраняются как исходники.

CI63b5248: Windows PASS; macOS15 full/core/native controls PASS, native auth FAIL.
Локальный target Mac27.0.1 auth21 PASS и frozen protected self-tests PASS. Причина
CI15 auth ещё не установлена; JUnit/annotations добавлены в workflow, чтобы
следующий сбой дал точную диагностику. Не обходить check и не мержить main
по одному локальному проходу. Новые design cases включены в native CI обеих ОС.

## 29 октября — новая иконка, исправления и обе поставки (текущая задача)

После design parity b789685 владелец разрешил Mac native checks, новый DMG и
установку поверх прежней версии. Mac27.0.1/arm64: 428 offline PASS/6 skips,
73 native PASS/1 Windows-only skip, frozen UI/local media + оба protected
WebEngine self-tests PASS. B789685 DMG проверен codesign/hdiutil, запущен через
Launch Services с read-only DMG и после установки в /Applications; 477 прежних
файлов профиля сохранились byte-identical. Это ad-hoc подпись без notarization:
spctl rejects, локальный запуск через LS фактически прошёл, защита не отключалась.

Затем владелец попросил Windows EXE в той же папке Мой диск/ClipFlow и проверку
в уже запущенном Parallels. VM Windows11 ARM64, x64 Python3.12.10 в эмуляции;
создан изолированный clone вне Drive. Не выдавать это за физический x64 Mac/PC.
Автопауза VM временно выключена для сборки, исходное Pause idle=on восстановить
после работы; личный Windows checkout/программу не заменять без отдельной команды.

Новые уточнения владельца в ходе задачи:
- Сохранить первый сгенерированный вариант и дать ещё пять; все6 PNG сохранены в
  assets/icon-concepts/2026-10-29 и личной папке выдачи. Выбран **1 — фиолетовый поток**.
  Производные1024 PNG, ICNS и multi-size ICO заменяют старую YouTube-похожую иконку.
  Одна иконка у приложения/side-brand/auth child/обоих установщиков; цвет площадки
  остаётся только в accents/индикаторах, app identity не меняется при смене сервиса.
- Обрезанные подписи режимов на всех площадках: ширина резервируется по semibold
  ink bounds и высоте; при широком fallback-шрифте caption «Скачать» уступает место
  режимам. Windows CI b789685 failed из-за EN880px горизонтального overflow;
  он воспроизведён в Parallels (composer646/viewport643) и исправлен без skip или
  ослабления ограничения. Windows UI suite35 PASS/1 native-only skip на рабочей
  копии патча; полный старый check в эмуляции превышал360s, это не success.
- «Несколько ссылок» скрыта в Settings/Accounts, видна в Downloads/History.

Финальные исходники: 435 offline PASS/6 explicit skips, core97.24% строк/91.60%
ветвей, runtime87.76%; native controls36 PASS и native auth21 PASS на Mac.
Windows patched UI35 PASS/1 native-only skip в Parallels, в том числе прежняя
EN880/DPI ошибка; последняя адаптация учитывает и explicit minimum caption width.
Новые тесты ожидают settled Qt layout, не меняя требований по ширине/высоте.
Иконка source/frozen/auth-child загружается из общего PNG, ресурс включён в specs;
frozen smoke требует non-null window icon.

Эти правки ещё требуют чистых сборок нового source SHA, frozen/native проверок
и повторной установки на Mac: установленный b789685 их пока не содержит.
Личные login/закрытые материалы GetCourse и IG profile10/50/all не проверены;
YouTube/Music public metadata PASS, выбранная публичная playlist fixture unavailable.
Соблюдать policy429, не создавать массовых профильных запросов ради отчёта.

## Актуальное уточнение — 29 октября: восстановление дизайна

Получен dev `bd2e049` с Windows-частью T16. Предыдущая память этого чата про T11
устарела. T1–T14 реализованы, T15-кандидаты собраны на другом ПК; Windows T16
имеет parity/live результаты, но независимый review/итоговый пакет по последнему
срезу ещё не завершены. Mac T16a остаётся открытым: `docs/MAC-T16A.md`.

Владелец попросил продолжить и вернуть внешний вид к скриншоту первоначального
утверждённого макета, затем уточнил: отдельные акценты близки к фирменным цветам
площадок (YouTube red, Instagram pink/purple, GetCourse green). Завершена отдельная
одна задача visual parity: [план](superpowers/plans/2026-10-29-clipflow-design-parity.md).
Рабочее место сейчас Mac checkout; Windows-пути из предыдущего среза не являются
указанием работать на Mac вне актуального Git checkout.

Изменения: светлый белый canvas/мягкая панель и соответствующая dark theme,
компактная форма с режимами справа, встроенная кнопка вставки, пояснение, summary
и disclosure; папка/автозапуск в раскрытии; группировка/живые счётчики sidebar,
аккаунты/настройки снизу; настоящие All/Active/Done/Error фильтры; painted строки
с неброскими действиями и прогрессом цвета сервиса. Нет подставных авторов,
миниатюр или статусов в runtime; screenshots используют только isolated QA jobs.
Сетевой/SQLite/auth/media код не перерабатывался.

На стартовом bd2e049 полный Cocoa check на этом Mac выявил 7 Instagram cases,
которые упирались в portable path limit из-за длинного per-test tmp root, и timeout
активации GUI в test_batch_shortcut_ctrl_command_n. Transfer fixture получила
короткий уникальный tmp root (production path protections сохранены); offline
suite запускается явно offscreen, native Cocoa clipboard/DPI отдельно. Нельзя
утверждать исправление активации приложения по offscreen результату.

Результат Mac27.0.1 arm64/Python3.12.15: 428 passed/6 explicit skips в полном
`QT_QPA_PLATFORM=offscreen python scripts/check.py`; core97.24% строк/91.60% ветвей,
runtime87.70% строк. Новых design cases10; mutation с общим accent вместо цвета
сервиса даёт3 FAIL, исходник восстановлен и полный suite снова GREEN. Отдельный
Cocoa input/DPI suite8 PASS/1 deselected: paste shortcut/button/context во всех
трёх сервисах, русские edit shortcuts, native clipboard с восстановлением,
масштабы100/150/200%. Cmd+N foreground activation всё ещё не принят на этом Mac.
Снимки реального Qt (isolated illustrative jobs) в docs/screenshots; README
обновлён, фото/авторы/состояния не подделываются в runtime. Windows exact-SHA
CI результата пока нет; локальная Windows QA этой правки не выполнялась.

Задача visual parity завершена; сохранить commit/результаты/Agents snapshot и пауза. Mac
Keychain/WebEngine/live/package/Finder/Launch Services/install часть T16a этим
изменением не закрывается. Установленное приложение/профиль не менялись; main
не мержить до общих exact-SHA и нативных gate результатов.

Записи отдельных T1–T15 ниже содержат исторические результаты соответствующих
этапов; при расхождении приоритет у этого раздела и последнего Agents snapshot.

## Что утверждено

Владелец утвердил переход на PySide6/Qt, направление интерактивного макета и письменную спецификацию. Разрешены планирование и последующая реализация. Одна кодовая база Windows/macOS, обязательная тёмная тема и проверенные сценарии — ключевые требования.

- Спецификация: [2026-10-27-clipflow-qt-design.md](superpowers/specs/2026-10-27-clipflow-qt-design.md).
- План: [2026-10-27-clipflow-qt.md](superpowers/plans/2026-10-27-clipflow-qt.md), 16 этапов T1–T16.
- Макет: HTML и три изображения в `docs/superpowers/specs/assets/`. Это демонстрация, не работающий Qt-клиент.
- План прошёл авторскую самопроверку и утверждён владельцем. Выбран Native: один исполнитель по этапам и независимая проверка всей ветки в конце. Повторное согласование плана/способа исполнения не требуется.
- Реализованы T1–T14: неизменяемые запросы, URL-маршрутизация, единое добавление, attempt-safe планировщик без виджетов, общий медиаконвейер, YouTube/Music, GetCourse и отдельные Instagram посты/Reels/карусели. T3 добавляет один активный worker, pause/resume/cancel/retry, новые attempt IDs, дедуп дочерних запросов, selection и rate-limit pause, подписки и отменяемые ожидания.
- T3: 28 тестов планировщика; всего 79 pytest-тестов и полный `scripts/check.py` (legacy regression scripts + self-test + pytest) прошли на macOS/Python 3.12.15. Покрытие нового ядра: 452/462 строк (97.84%), 140/150 ветвей (93.33%); scheduler — 100% строк, 70/72 ветвей. Это текущее ядро T1–T3, не покрытие будущего полного приложения. Windows/пакеты в этой сессии локально не проверялись.
- T4 выполнен на Windows 11 x64 / Python 3.12.10 / FFmpeg и FFprobe 9.0.2: 47 новых тестов, 126 всего; полный `scripts/check.py` пройден. Domain/application: 521/532 строк (97.93%), 169/180 ветвей (93.89%); весь текущий `src/clipflow`: 768/791 строк (97.09%), 218/242 ветвей (90.08%). Это покрытие реализованной части T1–T4, не будущего полного Qt-приложения.
- T4: безопасные Unicode/Windows-пути с резервом для временных файлов, исходные номера, уникальные папки/имена постов, отдельные коды с разным регистром; общие Provider/ExecutionContext/MediaItem/ProbeResult/DownloadResult. YoutubeDL скачивает во временный источник, FFmpeg обрабатывает и проверяет результат перед публикацией. Совместимый WebM remux без перекодирования, несовместимый — VP9/Opus; фото сохраняют байты/расширение. Повтор не перезаписывает готовое медиа; TXT/MD пишутся через fsync/atomic replace. Ошибки имеют безопасный MediaFailure.code, FilesSaved выдаётся только после успешного сохранения; отмена сохраняет partial/source и завершает дочерний процесс до возврата.
- Провайдеры Instagram в T7 должны нормализовать transient `MediaItem.info`: `author`, `post_code`, `post_title`, `published_at` (datetime), `description`, `ext`; raw info не попадает в историю. Коды с нижним регистром получают суффикс `~hex` (позиции заглавных букв), чтобы разные case-sensitive коды не столкнулись на Windows/macOS. Слишком длинный выбранный корень отклоняется, а не перенаправляется; имена временных файлов имеют запас длины.
- T4 дополнительно сохраняет требуемые extractor `http_headers` при загрузке фото (включая Referer). Первый Windows CI выявил ошибку только тестового FFprobe helper: системная cp1252 вместо UTF-8; helper исправлен с проверкой Unicode-пути, production уже читает bytes/JSON без locale decoding.
- T5: общий YouTubeProvider для обычных и music.youtube.com ссылок, probe доступных высот/аудио, отдельные canonical child requests плейлиста. 27 новых тестов (24 unit + 3 интеграционных с локальным HTTP/FFmpeg), 153 pytest всего и полный scripts/check.py прошли на Windows/Python 3.12.10. Domain/application: 539/550 строк (98%), 177/188 ветвей (94.15%); текущий src/clipflow: 884/908 строк (97.36%), 260/288 ветвей (90.28%). Это покрытие реализованной части, не будущего полного приложения.
- T5 добавил frozen PlaylistPosition(playlist_id,index) в DownloadRequest.playlist (по умолчанию None). Сохраняется исходная позиция, входит в request_key; T9 должен сериализовать это поле. Видео плейлиста сохраняются в отдельной стабильной папке ID плейлиста с portable case marker и именами 001 - Название.ext. Известный private/unavailable ID остаётся отдельным заданием с собственной ошибкой; элементы без ID пропускаются, номера последующих не сдвигаются. Перечисление выдаёт партии ≤25; повторное выполнение дедуплицирует T3. Lazy entries yt-dlp читаются внутри lifetime downloader; ошибка страницы — безопасный probe_failed, без ложного завершения.
- Авторизация передаётся через ephemeral AuthGateway options; raw info/CDN headers остаются только в памяти. MP3 не называется lossless, исходное качество не повышается преобразованием. Общая телеметрия T4 ограничивает burst 3000 callbacks/3s до ≤7 событий, FilesSaved остаётся после processing. Живой YouTube/Music, настоящая сессия и новые пакеты здесь не проверялись: synthetic metadata + реальный local HTTP/FFmpeg не доказывают доступность площадки. Auth adapters остаются T13, live checks — T16.
- T6: GetCourseProvider, scoped LessonExtractor/PlayerExtractor без глобального patch старых классов. Полные названия урока/материалов, вход с подписанным школьным requestTime вместо локального времени; player02/vhcdn/gceuproxy маршруты. Несколько видео требуют SelectionRequired; явный набор выбранных ID разбивается на независимые child requests с selection=(id,). Каждый child заново сверяет урок и конфиг плеера по стабильному video_hash/ID; отсутствующая/подменённая выборка даёт getcourse_selection_changed. Не угадывать ID из временной подписи/номера iframe.
- T6: общий providers/access.py для всех провайдеров/медиаконвейера. cookiefile/_cookies_source читаются в память, имя исходного файла удаляется из yt-dlp options, обратной записи нет. Netscape строки проверяются до загрузки: yt-dlp иначе печатает повреждённую строку напрямую, минуя logger. Ephemeral _cookiejar передаёт сессию школьного login в фактическую загрузку медиа; browser cookies и username/password идут через AuthGateway. Никаких реальных браузеров, паролей или защищённого хранилища в тестах; T13 ещё должен подключить реальные адаптеры/UI.
- T6: GetCourse файлы разнесены по стабильным подпапкам урока/плеера (короткий hash идентичности, без исходных signed URLs/секретов в имени); обычные названия видео остаются читаемыми. Это предотвращает использование чужого одноимённого готового файла; существующие файлы/legacy layout не перемещаются.
- T6: 30 тестовых случаев (включая два actual local HTTP/FFmpeg), 183 pytest всего и полный scripts/check.py PASS на Windows 11 x64/Python 3.12.10/FFmpeg 9.0.2. Domain/application: 549/560 строк (98.04%), 181/192 ветвей (94.27%); текущий src/clipflow: 1147/1179 строк (97.29%), 349/388 ветвей (89.95%). Это реализованная часть, не весь будущий Qt runtime. Живой урок/реальные сессии не проверены; T16. Ошибки школы имеют GetCourse-specific безопасные коды без Instagram/Brave hints.
- T7: InstagramPostProvider + scoped InstagramExtractor переносят проверенную photo adaptation без App.worker. Отдельный пост не разворачивает профиль; img_index не обрезает карусель. Фильтры сохраняют исходные номера, фото сохраняют оригинальные байты/расширение; TXT/MD парные и без пустых файлов. Папки автора/поста независимы; без подписи/без папки поста разные коды не перезаписывают соседа. Первый failed item останавливает пост с InstagramMediaFailure(media_id,index,reason), безопасной строкой index/reason для T10; прежние FilesSaved и готовые файлы остаются, retry переиспользует их. Более поздние элементы не объявляются готовыми.
- SessionAuth вынесен в общий providers/access.py и используется GetCourse/Instagram: обновлённая cookie-сессия metadata передаётся медиаконвейеру в памяти, экспорт/username/password не записываются в результаты. Без context.instagram_rate новый InstagramPostProvider отказывает до сети. Встроенные retries/fragment retries для Instagram отключены. На момент T7 acquire(metadata/post) ещё не покрывали все HTTP. T8 заменил их transport gate, включая upstream initialization/homepage, redirects, API/probe и CDN; UI wiring остаётся T10.
- T7: 36 новых случаев (20 unit + 16 local HTTP/FFmpeg), 219 pytest всего и полный scripts/check.py PASS на Windows/Python 3.12.10/FFmpeg 9.0.2. Domain/application 549/560 строк (98.04%), 181/192 ветвей (94.27%); текущий src/clipflow 1297/1337 строк (97.01%), 399/442 ветвей (90.27%). Это реализованная часть. Первая T7 попытка позволила upstream homepage initialization до тестовой подмены; не считать её offline/live-content приёмкой. Исправлено: init изолирован и urlopen в T7 тестах разрешает только loopback. Последующие 219 тестов — с этой защитой; реальные посты/аккаунты/успешное скачивание Instagram не проверены, остаются T16.
- Критический контракт T3: команда stop не освобождает слот. Только WorkStopped/WorkFinished/WorkFailed после teardown позволяет старт следующего worker. Поздний callback старой попытки ничего не меняет. Executor T10 обязан доставлять callbacks на поток-владелец scheduler/SQLite через queued Qt signals.
- Профиль завершает перечисление отдельно от скачивания дочерних файлов; найденные дубли не создают повторных jobs. WorkFinished без файлов/найденных материалов даёт failed/no_output. Выбор материалов создаёт новый снимок request. Instagram pacing/автоповторы и persisted cooldown добавлены T8; постоянная база очереди/восстановление — T9.
- Прямое указание владельца: **после каждого этапа пауза**. T10 завершён; остановка перед T11. T11 не начинать без команды владельца. Qt-интерфейс и новые установщики ещё не реализованы, установленное приложение не менялось. Новые live-content/native Mac/package проверки здесь не выполнялись. Независимый review всей ветки остаётся T16.

## T8 — Instagram profiles и общий HTTP budget

- 28 октября владелец подтвердил рабочий Git checkout `C:/Users/Kirill/PycharmProjects/ClipFlow`, несмотря на старый AGENTS в Drive Windows. Историческую папку не менять.
- `InstagramProfileProvider` валидирует probe без сети; execute перечисляет один раз, дедуплицирует feed/Reels и выдаёт партии ≤25. Для последних 10/50 при неизвестном порядке полный обход до исчерпания, сортировка UTC дат и учёт pinned независимо от позиции; незавершённый обход не выдаётся за точный latest N. All mode оставляет уже найденные jobs при последующей ошибке.
- `InstaloaderPageSource` переиспользует memory-only session/RateController, ограничивает timeout/retries, покрывает реальные clones get_json и прямой homepage request. Смена auth fingerprint закрывает старый клиент; T10/T13 обязаны вызвать close на shutdown/logout. Сессии не переносились и не сохранялись в проект.
- Общий `InstagramRatePolicy` и отдельный schema-v1 `instagram-rate.sqlite3`: cross-process reservations, response-body lease с heartbeat, UTC timestamps, monotonic bound ожидания, rollback защита, 3s metadata / 10–20s post/page. Retry-After seconds/date + library deadline + positive jitter; fallback 900/1800/3600, только первые два отказа допускают automatic retry. CDN читается без покусковых sleeps, Instagram fragment concurrency 1.
- Scoped yt-dlp transport использует urllib только для Instagram, включая redirect pacing и отмену без преобразования в NoSupportingHandlers; upstream registry не изменён. Имплицитные retries отключены, 429 превращается в RateLimitDeferred + WorkCancelled до worker ACK. Worker освобождается только после teardown по контракту T3. Scheduler пропускает другие Instagram jobs во время cooldown, запускает YouTube/GetCourse и возобновляет разрешённые retries через owner-thread tick. User pause выключает automatic retry.
- Checkpoints содержат safe progress cursor/codes/completeness; completed IDs сохраняются отдельно. Instaloader iterator cursor не считается portable API: resume безопасно перечисляет заново, T3 дедуплицирует очередь, pipeline переиспользует проверенные готовые файлы. Checkpoint не является durable queue ACK; T9 реализует очередь отдельно.
- 38 новых случаев, всего 257 pytest и полный scripts/check.py PASS на Windows 11 x64/Python 3.12.10. Включены local HTTP/FFmpeg, actual redirect/clone/session paths, cross-process SQLite, отмена, private access, partial queue retry и 5000 synthetic posts вне главного потока. Coverage core 655/674 строк (97.18%), 209/230 ветвей (90.87%); весь текущий src 1711/1784 строк (95.91%), 495/566 ветвей (87.46%). Legacy yt-dlp ResourceWarning известен и остаётся exit 0.
- T9 должен сохранять Job.automatic_retry и PlaylistPosition, но восстанавливать прерванные jobs paused/automatic_retry=False без автосети. T10 передаёт один общий policy во все IG contexts/probes, вызывает scheduler.tick на owner thread и закрывает source. Новый Qt UI, live Instagram/аккаунты, native Mac вручную и новые пакеты ещё не проверены; installed runtime/main не менялись. Независимый review — T16.

## T9 — постоянная очередь и настройки

- `SqliteJobRepository` хранит очередь и terminal history в отдельном `queue.sqlite3`, schema1. Add/update/recover/clear — короткие atomic transactions, synchronous FULL, bounded busy timeout; ошибки read-only/busy/full/corrupt имеют безопасные коды. Unknown schema и corrupt DB не пересоздаются. JSON payload сверяется с SQL identity и строгими типами; URL/traceback в error не сохраняются. Snapshot включает PlaylistPosition, selection, parent, paths, deadline, automatic_retry и source_required.
- `recover()` вызывается явно при старте T10. Queued/probing/downloading/processing становятся paused/restart, attempt сбрасывается; прежняя rate_limit/user pause и deadline сохраняются, automatic_retry=False. Никакой сети. Готовый файл после разрыва между media publish и DB commit сверяется pipeline только при явном resume, без повторной записи (mtime сохранён).
- Подписанные/неизвестные GetCourse sources не пишутся в БД: разрешённые обычные lesson id/editMode сохраняются, остальное — opaque SHA-256 reference и root host; полный URL живёт только в памяти текущего repository. После рестарта `Job.source_required=True`, scheduler блокирует start/resume/retry/select до `provide_source(id, ParsedLink)`. Сверяется та же canonical source identity; другая/ротированная подпись — новое задание, прежние файлы не удаляются и не приписываются новому источнику. GetCourse request_key нормализован через idempotent reference, поэтому повторный ввод не удваивает восстановленную очередь.
- `SettingsStore` пишет `settings-v2.json` через same-directory temp + fsync + atomic replace (directory fsync на POSIX). `AppSettings` immutable, presets по Service, dark/ru/auto_start=False/limit10 по умолчанию, 10 недавних папок. Profile references только opaque ASCII IDs ≤64, не email/password/cookie/export paths; T13 сопоставляет их прежнему protected storage.
- Migration читает whitelist из settings.json, сохраняет нормализованную копию поддерживаемых параметров в settings-v1.*.bak, исходный legacy файл и protected sessions остаются побайтно нетронутыми. Unknown/nested fields не попадают в backup/v2. Цена: backup содержит поддерживаемые preferences, а не все неизвестные legacy fields; нетронутый оригинал остаётся. Legacy auto_download не включает новый auto_start. Повреждённый v2 (включая encoding) получает backup, defaults и last_warning; неизвестный schema_version любого типа не перезаписывается.
- `clear_history` удаляет terminal rows без удаления медиа. Terminal ancestors активных дочерних jobs сохраняются для целостности subtree; после завершения детей их тоже можно очистить. Хранилище используется потоком-владельцем scheduler, T10 закрывает его после завершения workers.
- 34 новых случая, 291 pytest и полный scripts/check.py PASS на Windows 11 x64/Python3.12.10. Core 674/693 строк (97.26%), 221/242 ветвей (91.32%); весь текущий src 2038/2129 строк (95.73%), 590/690 ветвей (85.51%). Native local media reconciliation, database/atomic-write failures, corrupt/unknown schemas, restart/dedup, credentials filtering и backup restore проверены. Legacy yt-dlp ResourceWarning известен, exit0.
- T10 должен подключить новые stores/registry к Qt, вызвать recover до показа/запуска очереди, предоставить UI source_required/re-entry и SettingsStore.last_warning, owner-thread scheduler.tick и shutdown close. Новый UI ещё не начат; installed legacy runtime, реальные сессии, main и пакеты не менялись. Live/native package/whole-branch review остаются T16.

## T10 — работающий Qt preview

- Вход `python run.py --qt-preview` или `python -m clipflow`; обычный run.py по-прежнему legacy до T16. Preview импортирует src package до любого legacy sys.path, без hidden Tk App. Bootstrap использует прежний LocalAppData/Library Application Support или CLIPFLOW_DATA_DIR, новые T9 settings/queue и T8 rate DB; recover до UI, без сети/автовозобновления.
- `ThreadExecutor` использует QThread, все события доставляются queued signals на owner thread scheduler/SQLite/model. Terminal ACK создаётся только после возврата run/teardown; pause/cancel держат слот до QThread.finished. После programmatic app quit main finally вызывает shutdown/drain и reaps threads, не уничтожает живой QThread. CloseEvent асинхронно ждёт остановки; repository закрывается после worker/source cleanup. Запись БД не удалась — worker отменён, очередь остановлена безопасно.
- Registry подключает YouTube/Music, GetCourse, IG post/profile к настоящему MediaPipeline и FFmpeg/FFprobe/Node lookup. Один InstagramRatePolicy во все worker contexts, reusable InstaloaderPageSource закрывается на shutdown. В preview PublicAuthGateway только для открытого контента; реальные прежние protected adapters/session/login остаются T13 и не затрагивались. Не выдавать public-only adapter за выполненный вход.
- Базовый dark workbench по утверждённому макету: sidebar all/history/services, single composer placeholder, mode/folder/auto-start, model/view queue с рисованным delegate и настоящими row pause/resume/cancel/open-folder, keyboard row activation. 1000 строк не создают 1000 widgets. Расширенный Composer/BatchDialog — T11; themes/RU-EN/native clipboard/DPI — T12, accounts T13, полная история/удаление файлов T14.
- `TitleChanged(title)` — transient событие metadata из MediaPipeline, не raw info/CDN. Model roles job_id/title/state/progress/files/source; progress updates только нужную строку, worker coalesces <=2Hz, critical stage/error/title без задержки, старый attempt игнорируется. После restart заголовок берётся из file stem/безопасного fallback, rich persistent metadata не добавлялось в T9 schema.
- `SelectionRequired` получил backward-compatible titles=(); GetCourse передаёт полные имена материалов. После восстановления IDs/titles не считаются свежими: явный refresh_selection запускает повторную проверку, пользователь выбирает актуальные IDs. Source-required dialog вызывает T9 provide_source, иной/rotated signed URL требует нового задания. Scheduler.start(job_id=None) может приоритетно запустить выбранный queued job без второго worker; обычный start сохраняет порядок.
- Принятая ссылка очищается только если поле всё ещё содержит тот же текст; неверная/дубликат остаются. Folder save failure не создаёт job с прежней папкой; auto-start failure возвращает checkbox к сохранённому состоянию. Unknown/corrupt/read-only startup storage показывается безопасным диалогом, last_warning settings показывается в workbench.
- 23 новых GUI-case, 314 pytest и полный scripts/check.py PASS на Windows/Python3.12.10/FFmpeg9.0.2, в том числе real local HTTP → YouTubeProvider → MediaPipeline/FFmpeg → настоящий MP4 → SQLite history. Проверены GUI timer при блокирующем provider, owner-thread model events, stale attempts, throttled progress, row mouse/keyboard actions, selection refresh, IG cooldown frees real executor for YouTube, asynchronous close/drain, storage failures, no per-row widgets.
- Coverage core 690/711 строк (97.05%), 226/248 ветвей (91.13%); текущий src 2556/2704 строк (94.53%), 687/824 ветвей (83.37%). QThread.run тела консервативно остаются missed у стандартного coverage tracer; executor не исключён из метрик, его поведение проверено GUI assertions. Известный legacy yt-dlp ResourceWarning — exit0.
- Native Windows preview действительно открыт из run.py в isolated profile, 1180×800 и 880×680 PNG проверены, no tkinter import, clean shutdown; QA link только queued, без живых запросов. CI Qt GUI выполняется offscreen через workflow env; это не native Mac/manual clipboard/DPI/auth/package/live acceptance. Installed runtime, реальные сессии, main не менялись; нет новой сборки/установщика. Независимый review всей ветки и live/package — T16.

### Коррекция T10 после CI macOS

Первый коммит 9540e90 прошёл Windows CI, но macOS не активировал row resume по Return. В Qt [activated() зависит от платформы](https://doc.qt.io/qt-6.10/qabstractitemview.html#activated); QueueView теперь явно обрабатывает Return и Enter цифрового блока, без повторной активации от autorepeat. Остальная навигация/нативные shortcuts остаются у QListView. Локальный RED доказал, что удержание Return раньше сразу повторно ставило job на паузу; regression GREEN и проверка обеих клавиш добавлены. Итог — 23 GUI/314 total; failed CI не обходился, нужен успешный новый SHA на обеих ОС.

## T11 — форма, пакетные ссылки и явные режимы

- Composer хранит отдельные черновики/режимы/параметры YouTube, Instagram и GetCourse. Видны Single/Batch/Profile/Playlist/Lesson; ссылка профиля в одиночном режиме требует явного выбора «Профиль». Лимиты Instagram 10/50/все, обязательная папка поста в profile не меняет предпочтение одиночного поста. Раскрываемые параметры: формат/качество/filter/папки/описание, выбор и 10 недавних путей.
- «Несколько ссылок» всегда видна в header, включая историю. BatchDialog показывает сервис, безопасный материал, параметры/папку, ошибки строк и повторы (в том числе уже в очереди). Настройки frozen на момент открытия, metadata network в preview отсутствует. Только явное подтверждение добавляет корректные строки через T2; отмена ничего не добавляет, storage failure оставляет текст/диалог. Batch не переключает и не очищает Single draft.
- Async quality: debounce300ms, новый request ID при изменении, устаревший ответ игнорируется; память-only cache100/120s, raw metadata не сохраняется. Best первым, доступные высоты убывают, сохранённый cap не выдается за доступный формат. MP3/фото показывают честное описание; коллекции не перечисляются второй раз ради quality.
- Probe и download используют один executor slot/shared IG policy/auth gateway. Запуск очереди отменяет optional probe и ждёт фактического teardown; нет worker_start_failed из-за занятости. Stale probe не очищает поле; принятая ссылка очищается лишь при совпадении текущего draft. После полного drain новые задания не запускаются timer/probe callback при auto_start=False; rate-limit automatic retry сохраняется.
- 21 submission GUI case + новый scheduler regression, 336 pytest и полный scripts/check.py PASS. Все обязательные T11 случаи проверены настоящими click/Enter/модальными формами до repository. Core700/720строк97.22%,229/250ветвей91.60%; src2900/3073строк94.37%,762/908ветвей83.92%. QThread bodies консервативно missed стандартным tracer, не исключены. Known legacy yt-dlp ResourceWarning остаётся exit0.
- Native Windows run.py --qt-preview с isolated profile: расширенные параметры при880×680 и mixed batch, no horizontal clipping, clean shutdown/no Tk/no upstream requests. После offscreen RED минимальная ширина URL180px закреплена в UI и проверяется вместе с отсутствием горизонтальной прокрутки; это не native Mac/manual DPI/clipboard приёмка.
- Legacy default/installed app/real sessions не менялись; новый установщик не создавался. Public-only preview auth остаётся до T13, темы/RU-EN/clipboard/DPI T12, полноценная история/файлы T14, final review/live/packages T16. Пауза после T11, перед T12; exact-SHA CI фиксируется в Agents snapshot/журнале.

## T12 — темы, RU/EN и системная клавиатура

- ThemeManager(app,settings) даёт dark/light/system, resolved_mode(), immutable tokens(). Тёмная по умолчанию; выбор темы/языка сохраняется через presenter/SettingsStore, storage failure возвращает прежнее оформление и checkmarks. System подписан на Qt styleHints colorSchemeChanged; фиксированная тема не меняется от системного события. Единая palette/QSS покрывает inputs, menus, dialogs, table/list, selection/focus, disabled/error/success. Все заданные пары обычного текста >=4.5:1. Сервис меняет только небольшие accent/icon, фон окна стабилен.
- Translator с явным каталогом RU/EN, форматированными ключами и weak bindings; нет поиска/замены русских строк в пользовательских данных. Уже открытый batch/selection/source dialog, labels, quality modes, errors, queue fallback/status/speed обновляются; drafts, options, probe IDs и реальные заголовки/пути не меняются. Qt qtbase translations подключаются для стандартных системных Qt controls, при наличии; native OS folder dialog использует системное оформление/язык. При упаковке T15 сохранить нужные .qm.
- Меню Загрузки/Правка/Вид/Настройки: batch, start queue, editing, темы и RU/EN. Используются QKeySequence.StandardKey (Qt сам отображает Command на macOS), не ручной выбор Ctrl/Meta по ОС. Cyrillic-layout copy/cut/paste/select-all/undo/redo, стандартные editing context actions; Clipboard QA сохраняет/восстанавливает все MIME-форматы, не пишет их на диск/в логи.
- На узком окне кнопка основной команды остаётся крупной и переносится на следующую строку, combos допускают сжатие; у advanced form вертикальная прокрутка без горизонтального обрезания. Qt DPI применяется один раз, отдельные GUI-процессы QT_SCALE_FACTOR1/1.5/2 проверяют логические880×680 и DPR с учётом Retina/нативной базы. Нового пользовательского zoom нет.
- 355 collected:354passed/1native-only skip в offline suite; полный scripts/check.py PASS Windows/Python3.12.10/FFmpeg9.0.2. Все19 T12 cases отдельно PASS в настоящей Windows GUI, включая clipboard/контекстные меню/русские сочетания/Ctrl+N и DPI1/1.5/2. Native run.py --qt-preview с isolated profile проверен/captured/viewed: обе темы, RU/EN, все сервисы, batch,880px,no upstream/Tk/jobs,clean shutdown. Старый initial native Ctrl+N RED был отсутствием реальной активации QApplication до посылки клавиш; проверка ждёт ApplicationActive/activeWindow, а не только флага QWidget. Не обходили реальный shortcut fake обработчиком.
- Core700/720строк97.22%,229/250ветвей91.60%; src3128/3302строк94.73%,812/966ветвей84.06%. Тела QThread остаются консервативно missed, не исключены. Known legacy yt-dlp ResourceWarning exit0. В CI добавлены отдельные GUI steps windows/cocoa; их результат на точном SHA фиксируется в журнале/Agents snapshot, не выводится из offscreen pass.
- Public-only preview auth до T13; полноценная settings/accounts page T13, история/файлы T14, installer/live/final review T16. Новый установщик не создавался; installed runtime/main/реальные LocalAppData sessions не менялись. Пауза после T12, перед T13.

## T13 — аккаунты и совместимая авторизация

- NativeAuthGateway подключён к executor вместо PublicAuthGateway. PlatformServices даёт protect/reveal/choose_folder; production data root прежний LocalAppData/ClipFlow или Library/Application Support/ClipFlow. DPAPI format/flag1/no entropy, Keychain ClipFlow/profile-encryption-key-v1, session.dat JSON-cookie-list, YouTubeAuth/InstagramAuth/web-profile/cache, Chromium profile name clipflow-auth-prototype и точные имена приложений входа сохранены. Тесты используют только ClipFlow Tests/profile-key-HASH(isolated-root); реальные сессии не читались и не переносились.
- Отдельный auth_process: обычный Qt WebEngine и прежние Chrome на iPad51/87, domain-scoped cookie snapshots, atomic encrypted writes, mode preferences без секретов. Пароль вводится на странице провайдера. HTTPS/SSO-навигация сохранена, HTTP/file/userinfo блокируются; адрес показывает origin/path без query и служебного HTML/data. Встроенный frame наследует сохранённую тему, язык берётся при запуске. Браузерная страница может иметь собственное оформление.
- run.py и bootstrap распознают --youtube-login/--instagram-login/--auth-self-test/--instagram-auth-self-test до создания downloader/Tk. Основной процесс не импортирует WebEngine. Parent Popen без cookie/password аргументов, один handle на сервис + межпроцессный QLockFile. Закрытие неблокирующее: уникальный nonce-файл на запуск, запрос до старта не теряется; после3s terminate, затем2s kill при необходимости. Родитель ждёт executor ACK и actual child exit; finally/drain тоже освобождает child. Self-test требует новый пустой каталог внутри изолированного root и не может затронуть существующий профиль.
- GetCourse: явная привязка к ссылке урока школы; email/password, Netscape export и стандартные browser profiles защищены в GetCourseAuth/gc-HOSTHASH.dat. Native options_for отказывает другой школе/сервису; browser/export jar содержит только выбранную школу и её subdomains. Общий player/CDN не определяет школу: direct player работает анонимно/по своей подписанной ссылке без передачи школьных credentials, для защищённого урока используйте ссылку школы.
- Legacy getcourse-profile.dat не содержит школу. «Импортировать прежний профиль» требует явного выбора школы и создаёт scoped copy. Исходный encrypted файл не меняется и не удаляется при logout: он мог обновиться в legacy процессе/принадлежать другой школе. После выхода он не активен и автоматически не используется; явный повторный импорт возможен. Это уточнение заменяет раннюю идею удаления по fingerprint. Выход удаляет только выбранную новую запись, YouTube/Instagram изолированы.
- Accounts/Settings sidebar и RU/EN: при сохранённой YouTube/Instagram session кнопка входа скрыта, выход доступен; GetCourse показывает сохранённый email с честным статусом «профиль сохранён», не выдуманным подтверждением сервера. Password поля masked, paste/контекст работают, поле очищается при закрытии. Settings использует те же persistence/theme/language commands и About. Probe cache очищается при смене auth, активный selected-service job при logout ставится на паузу; остальные сервисы не затрагиваются. T8 Instaloader fingerprint уже обновляет/сбрасывает контекст при смене cookies/logout, rate budget не сбрасывается.
- Ошибка settings.save не фиксирует auth snapshot раньше записи, повторная синхронизация работает после восстановления доступа. Очередь/настройки хранят только opaque auth refs; support_status и ошибки не содержат cookies/password/email. Уже созданные requests сохраняют frozen ref; новый профиль используется новыми requests, а не тайной заменой параметров старого job.
- Проверки:384collected,379passed/5guarded native-only skips + полный scripts/check.py PASS. Отдельно29/29 T13 native Windows PASS: старое/новое шифрование roundtrip, оба QtWebEngine self-tests с локальной страницей/блокировкой upstream, domain removal, light theme, UA, delayed icon, process singleton, закрытие сразу при delayed startup, собственные clipboard fields с восстановлением MIME. Native run.py preview accounts/settings880px captured/viewed, generated protected profiles, no WebEngine/Tk in parent/no upstream/jobs, clean exit. No real Google/Instagram/GetCourse server login/closed media/package acceptance; T15/T16.
- Coverage core: 700/720 lines 97.22%, 229/250 branches 91.60%; весь src runtime: 3545/3969 lines 89.32%, 908/1174 branches 77.34%. Для честного порога explicit morfs включает каждый .py, в том числе не импортированный parent-процессом auth_process/window.py с консервативным0 (native CLI behaviour доказан отдельными assertions). QThread bodies тоже не исключены. Known legacy ResourceWarning exit0. Обе CI ОС дополнительно запускают native protected-auth suite; точный результат/SHA — в журнале и Agents snapshot.
- Installer/main/installed app/настоящий LocalAppData не менялись. Legacy normal run.py остаётся default до T16; Qt — run.py --qt-preview. Пауза после T13, перед T14; independent whole-branch review/live/packages остаются T16.

## T14 — история, файлы и безопасное завершение

- История показывает реальные завершённые записи, отдельный счётчик и отсутствие файлов после удаления/перемещения. Контекстное меню: папка результата, повтор по сохранённому request, убрать запись, удалить записанные файлы. RU/EN; никаких URL-field replay.
- Очистить очередь / историю — отдельные команды меню загрузок без подтверждения, файлы остаются. Планировщик прекращает dispatch перед отменой, удаление записей очереди ждёт teardown ACK; предки сохранённых дочерних записей остаются. Очистка истории/индивидуальная очистка ждёт idle, чтобы CANCELLED ещё работающего worker не потерял запись.
- Физическое удаление только после явного подтверждения Yes, No по умолчанию, и executor idle (включая ожидание teardown ACK после Cancel). Проверка всего выбора перед первым unlink: terminal jobs, только записанные файлы внутри исходного корня; запрет symlink/junction/traversal/directory/outside и корня активной загрузки. Никаких recursive delete и угадывания sidecar. История сохраняет записи путей, при отсутствии файла показывает «Файлы отсутствуют»; частичный FS failure сообщает ошибку и обновляет наличие. SQLite/файловая система не являются одной транзакцией.
- Отмена scoped yt-dlp request/read проверяется до/после операции с socket timeout≤5s, без повторного сетевого запроса после cancellation. Instagram сохраняет прежний paced transport и lease. Встроенный yt-dlp FFmpeg merger/fixup также исполняется через управляемый cancellation runner: instance-only adapter run_pp/real_run_ffmpeg для pinned yt-dlp, без global Popen patch. При отмене Windows taskkill /T /F останавливает дерево до ожидания pipes (Chocolatey EXE shim создаёт дочерний FFmpeg); POSIX запускает отдельную сессию и останавливает process group с SIGTERM/SIGKILL. Регрессия с реальным wrapper/child, удерживающим stderr, подтверждает завершение дочернего process handle. Настоящее объединение отдельных audio/video tracks проверено FFprobe; mtime и аргументы processor сохраняются. Timeout — граница cooperative I/O, не обещание остановить произвольный зависший OS/DNS/сторонний вызов.
- Закрытие ждёт worker/process/auth ACK, затем закрывает SQLite/окно. Тесты используют настоящий stalled localhost HTTP, длительный FFmpeg (собственный и внутренний yt-dlp), реальный управляемый child; процессы завершены/ожиданы. Restart остаётся paused. Реальный файл опубликован, затем инъекция DB-write failure до FilesSaved commit; явный retry после restart проверяет/использует файл без повторной записи/изменения mtime.
- Local full scripts/check.py: 402 passed, 6 skipped in 112.41s (0:01:52). Native Windows history/shutdown/clipboard/DPI suite и визуальные captures истории/подтверждения — отдельные isolated проверки; CI выполняет этот же native набор и T13 auth на обеих ОС. Symlink case на Windows без привилегий явно skipped, macOS выполняет его. Core: 705/725 lines (97.24%), 229/250 branches (91.60%). Все собственные src .py: 3746/4180 lines (89.62%), 957/1236 branches (77.43%); child-only UI/QThread остаются в знаменателе, без исключений ради покрытия.
- Рабочая папка повторно подтверждена владельцем: C:/Users/Kirill/PycharmProjects/ClipFlow. Old Drive Windows read-only. No installer/main merge/install, no real account/session operation. Legacy normal run.py default до T16; Qt preview --qt-preview. Пауза после T14 перед T15 (покрытие/CI/нативные пакеты).

## T15 — сборка нового Qt-кандидата (в работе)

- Единая версия `src/clipflow/version.py`: 2.0.0; dynamic project metadata, Windows PE version resource, macOS plist и Qt title/About берут её. `source/version.py` — только совместимый shim до T16; установленная/stable 1.8.7 не заменялась. Native specs обеих ОС используют `src/clipflow/__main__.py`, общий package_config; Tcl/Tk/customtkinter/legacy source исключены. Прежние Windows AppId и com.clipflow.desktop сохранены, minimum macOS27/arm64.
- `scripts/check.py --qt` запускает новый pytest + coverage; `check_coverage.py` по умолчанию делает fresh run, `--reuse` принимает отчёт только с совпадающим fingerprint всего src runtime. JSON включает все собственные .py (в том числе child-only UI), пороги 95% core lines /90% core branches /85% runtime lines. Локально411passed/6explicit skips;97.24%/91.60%/87.55% соответственно.
- `build.py` создаёт свежий UUID stage, не наслаивает установленную папку; explicit tool paths передаются после очистки DLL PATH. Метаданные build-report: commit/dirty/source fingerprint/OS/CPU; final candidate берётся из clean exact-SHA workflow. Standalone CLI self-tests fenced fresh CLIPFLOW_DATA_DIR, реальный Qt/local HTTP/FFmpeg/probe, screenshots и frozen proof; оба WebEngine self-tests подтверждают render, режимы UA и protected synthetic snapshot, не реальные аккаунты. Raw source, caches, profiles, legacy modules и внешние bundle symlinks проверяются package_smoke.
- Локальная Windows11 build28000 AMD64 diagnostic build прошла frozen native smoke без venv/PYTHONPATH/PATH инструментов и innounp CRC всех3062 entries; PE version2.0.0. Это dirty diagnostic candidate, не финальная выдача. Exact-SHA Windows/macOS package/check workflows и отчёты фиксируются в журнале/continuation pack после завершения.
- В package workflow manual matrix Windows/macOS15 arm64, включая native package smoke, codesign/hdiutil verification и JSON provenance; push/PR workflow продолжает Qt suite/coverage плюс нативные clipboard/DPI/history/shutdown/auth. macOS15 direct binary smoke не доказывает Launch Services minimum27.
- Владелец согласился сам проверить готовый DMG на Mac27.0.1. Пока результата нет, T15 acceptance НЕ завершён; T16, main merge/tag/release/installation не начинать автоматически. Актуальный Windows путь выдачи EXE/DMG хранится в личной внешней памяти по последнему указанию владельца (не hardcode build scripts).

## Исходная база

Актуальный runtime — 1.8.7, коммит `5f9cc8f`. Он получен из GitHub на Mac. Ранее эта переписка закончилась 1.8.6, но Windows-работа добавила восстановление иконки и изоляцию DLL PATH для упаковки. Эти исправления необходимо сохранить.

`source/clipflow.py` — прежний CustomTkinter-монолит; PySide6 уже используется отдельным окном авторизации. Есть yt-dlp, Instaloader, FFmpeg/Node и 11 legacy regression scripts. На 27 октября существующий `scripts/check.py` прошёл на Mac 27.0.1 arm64. Локальный лог: `work/qt-migration-baseline-macos.log`. Это baseline старого кода, не доказательство будущего Qt и не свежая Windows-проверка.

Версия 1.8.6 реализовала MP4/MKV/WebM/MP3, отдельные Instagram-посты/карусели, папки автора/поста и парные описания. Реальная карусель `DeR11OUkobq` ранее скачалась: 11 фото с описаниями. Массовое получение профиля ранее получило HTTP 429; успешный сквозной профиль не подтверждён.

## Основные решения новой версии

- Python 3.12, Qt Widgets, model/view очередь. Новое импортируемое ядро в `src/clipflow`, без скрытого legacy App.
- Dark по умолчанию, light/system доступны, выбор сохраняется, RU/EN.
- Единая команда добавления для одиночного поля, батча и профиля. Не завязывать создание задания на quality_pending или активную вкладку.
- В Instagram явные «Один пост», «Несколько ссылок», «Профиль»; лимит 10/50/все. Ссылка на профиль не должна случайно скачивать профиль из режима одного поста.
- Один одновременно исполняемый job, неизменяемые настройки задания, attempt IDs для защиты от поздних событий, мягкая пауза, отмена и настоящий прогресс.
- SQLite для истории/очереди, версионированный JSON настроек, прежние DPAPI/Keychain/каталоги и сессии. После рестарта прерванные задания paused, без автосети.
- pytest/pytest-qt/coverage; core 95% строк/90% ветвей, весь собственный runtime 85% строк. Нативные/package/live проверки не заменяются mocks или процентиком покрытия.
- YouTube Music — общий провайдер YouTube с отдельной проверкой треков/плейлистов. Spotify audio в объём не входит; официальный API не предоставляет скачивание полного аудиофайла.
- Дополнение владельца: общий Instagram rate gate/pacing и persisted cooldown, а не только network timeout. Правила и источники в [INSTAGRAM-RATE-LIMITS.md](INSTAGRAM-RATE-LIMITS.md), включены в spec/T8. Стартовые интервалы 3s metadata, 10–20s posts/pages, Retry-After/более длинный срок библиотеки, fallback 15/30/60 минут и ограниченные повторы; нет гарантии отсутствия 429. Это реализовано в новом ядре T8 и проверено offline; существующий legacy runtime не переключён, live проверка остаётся T16.

## Незакрытые проблемы старого UI

Владелец сообщил, что окно нескольких ссылок не работает и скрыто в меню. Чтение кода выявило конфликт с проверкой качества и неправильную маршрутизацию Instagram-profile как GetCourse. Эти случаи закреплены red-тестами T1/T2/T11; до реализации нельзя заявлять, что старый баг исправлен.

## Git и внешняя память

Работа — `dev`; `main` — стабильная. Перед работой fetch/status/pull --ff-only без потери чужих изменений. Merge только после checks обеих ОС точного SHA и необходимых нативных проверок. Исходники передаются между компьютерами GitHub, не копированием `.git` через Drive.

По указанию владельца папка `Agents/ClipFlow` содержит внешнюю память, копии specs/plans/mockups и датированные срезы. Обновлять после принятого решения/этапа/коммита/проверки, указывать что выполнено, что не выполнено, SHA, окружение и следующий шаг. Конкретный путь к Agents определить на данном компьютере; не переносить Mac-пути на Windows вслепую. Документы в репозитории — канонические для проектирования, внешние копии — комплект продолжения. Секреты, cookies, `.venv`, `.git`, временные медиа и логи с личными данными туда не копировать.

Историческая папка `Kas-common/ClipFlow/Windows` на Google Диске не изменяется. Собственный код без открытой лицензии, сторонние лицензии сохраняются.

## Следующий шаг

После текущей visual parity задачи пауза до команды владельца. Затем продолжить
Mac T16a по docs/MAC-T16A.md с новым SHA, сверить состояние Windows review и
повторить cross-platform CI. Пакеты до исправления дизайна являются прежними
кандидатами; не выдавать их за сборку с новым интерфейсом.

## 2026-10-29 — scope update: T16 Windows

Owner explicitly authorized finishing all Windows T16 work while no Mac is available.
Continue in C:/Users/Kirill/PycharmProjects/ClipFlow (reconfirmed after conflicting Drive instructions).
T16 is in progress: 70 replacement parity cases passed; legacy runtime retirement is underway.
Mac work must be performed on a Mac: native Cocoa/clipboard/DPI/auth, final macOS packaging,
Launch Services on macOS 27.0.1, install/upgrade preserving the profile, cleanup of temporary
registered apps, and final DMG verification. Existing T15 DMG is a candidate, not Mac acceptance.
Do not mark Mac T15/T16 complete or infer success from Windows/mock tests.

## 30 октября 2026 — установка последней поставки на основном Windows ПК

По прямому указанию владельца прочитаны актуальная Agents-память и новые Mac-коммиты; основной checkout dev обновлён ff-only до a3b13bc. Прежние два локальных изменения сохранены в именованном Git stash, не восстановлены поверх нового upstream.
Установлен существующий проверенный ClipFlow2.0.0 candidate в Program Files/ClipFlow, compiled source bfd5726c408068dc94ecb580a04d8d4c05dfa938 (runtime идентичен verification head d09a1dc и documentation head a3b13bc).
EXE SHA256 702751e66a4b175a3986c07126c53d4f724b191a96eecf346dc572376b2aec96; innounp integrity3058entries PASS; installer exit0, reboot не требуется. Ярлык Public Desktop указывает на установленный ClipFlow.exe.
До обновления541файл LocalAppData/ClipFlow скопирован в локальный ClipFlow-Backups и проверен по SHA256; после installer все541без изменений. Ничего из профиля не отправлялось в Git/Drive.
Выявлены1319лишних файлов от прежних overlay-установок, в том числе Tcl/Tk/старые Qt DLL. После полного сравнения с SHA-проверенным portable ZIP они перемещены пофайлово в тот же локальный backup; текущие package files, uninstaller и language.txt сохранены. Рекурсивного удаления не было.
На реальном Windows11 build28000 AMD64 именно установленная поставка прошла frozen Qt/local HTTP transfer/FFmpeg/FFprobe/Node и оба protected WebEngine self-tests на synthetic data, clean resources PASS. Это дополняет прежнюю Parallels ARM64 проверку. Личный вход/закрытые материалы этими self-tests не подтверждаются.
Текущие открытые Mac/manual/live gates из T16a и FINAL-REVIEW не закрываются установкой на Windows. Main не менялся, новый бинарник не пересобирался: установлен проверенный существующий артефакт.

## 2.0.1 — YouTube Music MP3

Ссылки с точным music.youtube.com сохраняют происхождение и принудительно создают MP3-задания: одиночный трек, плейлист, batch и дочерние задания очереди/restart/retry. Виджет показывает заблокированный MP3, обычный YouTube сохраняет предыдущий ручной формат даже после изменения папки в Music-режиме.
MP3320кбит/с из лучшей доступной аудиодорожки; исходное качество ограничено YouTube. Предыдущие192кбит/с файлы не считаются320кбит/с результатом и не перезаписываются. Папки плейлистов начинаются с настоящего title, затем portable ID; позиции001 сохранены. Старые SQLite записи без title читаются; title не меняет ключ дедупликации.
Живая public metadata проверка Sound City/PLO5Q7HxgkOYo получила46позиций; ограниченная попытка скачать первые2 упёрлась в HTTP403 на audio CDN без авторизации. Это unverified live transfer, не успешная загрузка; реальные профили не использовались. Real localhost FFmpeg/FFprobe MP3/audio-only320000bit/s PASS.
Windows2.0.1 package verification in progress; Mac native2.0.1 requires a Mac. Existing2.0.0 Mac/manual/live acceptance notes remain separate.
