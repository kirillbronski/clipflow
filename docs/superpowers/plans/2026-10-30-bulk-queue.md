# Управление всей очередью

Основание: прямой запрос владельца30 октября: отменить всю очередь, очистить
все загрузки одним действием, опционально удалить файлы галочкой в диалоге.
Общий Qt runtime Windows/macOS; изменения только в dev.

1. Regression tests: отмена active+waiting разных площадок, отсутствие запуска
   следующего worker, подтверждение No, clear-all parent+children, keep files,
   opt-in deletion после ACK, ошибка удаления без автоматического retry,
   containment и скрытие кнопок в Settings/Accounts, RU/EN при880×680.
2. Видимые кнопки рядом с запуском очереди: «Отменить очередь», «Очистить всё».
   Отмена оставляет записи/файлы. Очистка охватывает все сервисы и историю,
   явно сообщает об этом в диалоге. Галочка permanent file deletion выключена.
3. Перед удалением дождаться idle worker. Использовать существующую проверку
   recorded output paths и containment; никаких recursive folder deletes.
   На ошибке сохранить записи и показать ошибку; не повторять destructive IO
   по таймеру. Новые задания после команды не удалять по старому снимку.
4. Full checks+native Windows/macOS, screenshots, clean installers, обновить
   обе установки и Drive artifacts, commit/push dev, память/Agents и пауза.
