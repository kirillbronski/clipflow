# T16a — работа на Mac

### Task 16a: Завершение выпуска и нативная приёмка на Mac

**Статус: native/package/install выполнены для4ce2c97; личная/live приёмка открыта. Выполнять на физическом Mac; Windows-проверки и runner macOS 15 не заменяют приёмку на macOS 27.0.1.**

**Предусловия:** получить актуальную ветку dev и Windows T16 commit; прочитать PROJECT-MEMORY и последний Agents/ClipFlow snapshot. Сохранить локальные изменения. Создать собственное Python 3.12 arm64 окружение, не переносить .venv, ключи или сессии между компьютерами.

- [ ] Запустить полный `python scripts/check.py` на Mac и сохранить SHA, macOS/CPU, количество тестов, пропуски и coverage gates. Перепроверить общие Windows/macOS CI для того же SHA. Устранять обнаруженные Mac-регрессии с regression tests; не считать прежний T15 DMG окончательным T16a.
- [ ] На настоящем Cocoa проверить светлую/тёмную/системную темы, RU/EN, Command и русскую раскладку, clipboard/context menu, Retina/DPI, минимальное окно 880×680, скролл и диалоги без обрезания. Зафиксировать реальные Mac screenshots.
- [ ] Проверить Qt WebEngine YouTube/Instagram, оба режима Chrome/iPad, Keychain и namespace совместимости, сохранение после перезапуска, выход, закрытие auth child. Synthetic self-tests обязательны; личный вход/закрытые материалы проверяет владелец. Не копировать реальные cookies в Git/Drive/отчёты.
- [ ] Проверить очередь/историю, Pause/Resume/Cancel, завершение HTTP/FFmpeg/process group, восстановление SQLite без автоматического возобновления сети, clear-list без удаления файлов и физическое удаление только после подтверждения.
- [ ] Выполнить разрешённые live checks YouTube video/playlist/Music, Instagram Reel/carousel/profile10/50/all с отменой и GetCourse доступного урока. Соблюдать общий Instagram cooldown; без массовой загрузки чужого профиля. Блокировки/нет сессии фиксировать отдельно как experimental, не подменять mocks.
- [ ] Из чистого точного SHA собрать на Mac `python scripts/build.py`: fresh .app, DMG и APP ZIP, frozen UI/local transfer/tool checks, оба embedded-auth self-tests, codesign --verify и hdiutil verify, отсутствие source/cache/log/profile/uninstaller в поставке, наличие обязательных QtWebEngine/FFmpeg/FFprobe/Node/yt-dlp assets и лицензий.
- [ ] На macOS 27.0.1 открыть .app из смонтированного DMG через Finder/Launch Services, затем проверить установку/обновление в /Applications и повторный запуск. Предварительно сохранить профиль; подтвердить сохранность настроек/Keychain/сессии. Direct binary launch на CI15 не доказывает этот пункт. Не обходить Gatekeeper молча; указать фактический статус ad-hoc/notarization.
- [ ] Оставить одну установленную копию .app: после проверки unregister/remove только собственные временные приложения, извлечь DMG, сохранить архивы. Не удалять профиль или чужие файлы.
- [ ] Сверить SHA256/размер/source SHA/dirty=False всех артефактов; обновить verification report, README/BUILDING/MEMORY/ROADMAP и Agents/ClipFlow. Доставить DMG/APP ZIP в согласованную папку релизов (на Windows D:/Gdrive/ClipFlow), сохранив предыдущий кандидат отдельно.
- [ ] Только после фактических Mac gate результатов завершить Mac-часть T15/T16a и межплатформенную приёмку. Не маркировать всё завершённым по одному Windows выпуску. Слияние/публикация следуют текущим правилам репозитория; никаких bypass failed checks.

**Результат:** воспроизводимая проверенная Mac поставка того же исходного релиза, отчёт с реальными результатами и явно перечисленными ограничениями. T16 Windows может завершаться независимо; T16a остаётся открытым до выполнения чек-листа на Mac.

## Фактический срез 30 октября

- Mac27.0.1 arm64/Python3.12.15:437PASS/6 explicit skips, core97.24%/91.60%, runtime87.79%; native Cocoa59PASS.
- Native clipboard/Command/RU, themes/RU/EN/DPI/min880×680 и auth synthetic self-tests пройдены; реальные screenshots в docs/screenshots.
- Clean4ce2c97 DMG/APP ZIP: codesign/hdiutil и frozen media/tool/auth checks PASS. Launch Services из read-only DMG и /Applications PASS;582 прежних profile files сохранены при замене.
- Одна installed app; собственные test app/build/archive copies очищены. Подпись ad-hoc, notarization нет; Gatekeeper не отключался.
- Public YouTube video/Music metadata PASS, playlist fixture unavailable. Личный вход, закрытые GetCourse и live IGprofile10/50/all не приняты.
- Final review обнаружил generic filename collision и collection-retry dedup; исправления требуют пересборки, дальнейший verification report определяет финальный source SHA.

Чек-лист выше сохраняет исходные условия приёмки; synthetic/network-mock checks
не закрывают личные/live пункты. Не называть публичным stable release до их оценки.

После добавления bulk buttons native controls проверены отдельно. Повторный
Cocoa suite:59PASS/1FAIL — foreground prerequisite в Command+N не выполнен
(тестовое окно не активировалось). Результат не считать PASS; закрыть ручной
приёмкой foreground shortcut. Это не падение нового clear/cancel теста.
