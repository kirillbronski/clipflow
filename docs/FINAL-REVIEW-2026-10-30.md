# Независимый review — 30 октября 2026

Область: Qt migration от ce1d84e до4ce2c97; пути/выдача файлов,
очередь и попытки, коллекции Instagram, auth/session boundaries и shutdown.
Review выполнен отдельным агентом, без редактирования production-кода.

## Подтверждённые замечания и исправления

1. **P1: разные YouTube/GetCourse media с одинаковым title получали один путь.**
   Реальный offline FFmpeg пример показал повторное использование чужого MP4
   и замену его sidecar. Теперь generic stem содержит стабильный suffix из
   media identity и заданного max-height; suffix не усечётся вместе с title.
   Старые файлы без identity не удаляются и не принимаются за новый результат.
   Instagram нумерация01.mp4/01.txt сохранена.
   Regression: `test_same_title_different_media_and_quality_cannot_reuse_output`
   RED→GREEN; реальный HTTP/FFmpeg `test_same_title_videos_publish_separate_media_and_captions`
   проверяет независимые файлы/описания, сохранность legacy файла и retry reuse.
2. **P2: retry отменённой коллекции дедуплицировал отменённых детей.**
   ControlledExecutor пример: parent completed, child cancelled, child worker
   не стартовал. Теперь terminal failed/cancelled дети и completed без файлов
   не блокируют новую discovery. Существующие completed outputs и active jobs
   сохраняют дедупликацию.
   Regression: `test_collection_retry_rediscovery_restores_terminal_children_without_outputs`
   RED→GREEN для cancelled/failed/completed; отдельный тест сохраняемых outputs.

63 unit path/scheduler и35 integration PASS/1 Windows-only skip на Mac.
Полный suite/новые clean artifacts определяются итоговым verification report.
После исправлений повторный независимый review не подменяет regression tests.
Других подтверждённых important/critical замечаний в отчёте нет; это не
доказательство отсутствия всех потенциальных дефектов.

## Открытая приёмка

Личный вход и закрытые материалы GetCourse, live Instagram10/50/all не проверены.
Массовая загрузка остаётся experimental; Mac ad-hoc подпись без notarization.
Stable main не обновлять без exact-SHA CI обеих ОС и соответствующей приёмки.

## Дополнительный scope: массовая очистка

После review владелец добавил bulk cancel/clear с optional permanent deletion.
Отдельный scoped review нашёлP2: глобальный delete flag распространял прежнее
согласие на новые IDs при двух подтверждениях до worker ACK. Исправлено: per-ID
consent snapshot; более поздний диалог без галочки отзывает удаление своих IDs.
`test_overlapping_clear_commands_keep_deletion_consent_per_snapshot` RED→GREEN.
Также empty clear не вооружает удаление будущих файлов; IO error очищает pending
operation, поэтому timer не повторяет destructive IO; записи на ошибке остаются.

Итог исходников после всех исправлений: Mac455PASS/6 explicit skips,
core97.26%/91.67%, runtime87.92%; native bulk/layout44PASS.
Foreground prerequisite Command+N отдельно не принят; подробности MAC-T16A.

Windows CI diagnostic a25553e выявил реальную регрессию minimum width после
добавления3 queue buttons. Адаптивный toolbar переносит controls и не расширяет
880px окно. Новые RU/EN wide-metrics tests RED→GREEN; исходный failing caption
тест сохранён. Full-check watchdog600s основан на измеренных354s CI Mac/474s VM,
тестовые условия/пороги и platform coverage не ослаблены.
