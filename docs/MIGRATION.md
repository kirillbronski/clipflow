# Миграция на единый Qt runtime

`python run.py` и `python -m clipflow` теперь запускают Qt. Старые source/CustomTkinter и 11 AST/script regression tests удалены после PASS всех 70 replacement parity cases; соответствие сохранено в tests/legacy-parity.json. Тестовый historical codec остаётся независимой проверкой wire compatibility, в поставку не входит.

Windows профиль LocalAppData/ClipFlow сохраняется. Для старой папки данных: сначала резервная копия, затем `python scripts/migrate_windows_data.py --source ABS_PATH`. Команда копирует только разрешённые settings/GetCourse opaque profile, сохраняет оригиналы и не перезаписывает существующие целевые файлы. Не передавайте папку установленной программы вместо папки данных. Сессии Google/Instagram отдельно не импортируются автоматически.

Legacy preferences мигрируют в settings-v2 без переноса секретов в открытый JSON. Native session encryption совместимо с прежним DPAPI/Keychain форматом. Перезапуск очереди всегда paused; подписанные media URLs/пароли не сохраняются как request. GetCourse school binding требует явного источника; неизвестный профиль не привязывать молча.

Mac миграция/upgrade/Keychain проверяются на Mac в T16a; успешный Windows тест не означает Mac приёмку. Не удалять старые backups и реальные профили.
