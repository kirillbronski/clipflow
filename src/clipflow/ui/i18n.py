"""Explicit RU/EN message catalogue; never translate user content by replacement."""
import weakref
from PySide6.QtCore import QObject,Signal,QLibraryInfo,QLocale,QTranslator

MESSAGES={
 'all_downloads':('Все загрузки','All downloads'), 'history':('История','History'),
 'local_note':('Файлы остаются\nна этом компьютере','Files stay\non this computer'),
 'batch_button':('+  Несколько ссылок','+  Multiple links'),
 'subtitle':('Все сервисы. Одна понятная очередь.','All services. One clear queue.'),
 'start_queue':('▷  Запустить очередь','▷  Start queue'),
 'empty':('Здесь пока нет заданий. Добавьте первую ссылку.','No downloads yet. Add your first link.'),
 'footer':('Файлы сохраняются локально  ·  ClipFlow 2.0 · preview','Files are saved locally  ·  ClipFlow 2.0 · preview'),
 'queue_count':('Очередь  ·  {count} {word}','Queue  ·  {count} {word}'),
 'job_one':('задание','job'), 'job_few':('задания','jobs'), 'job_many':('заданий','jobs'),
 'service':('Сервис','Service'), 'profile_posts':('Публикации профиля','Profile posts'),
 'last_10':('Последние 10','Latest 10'), 'last_50':('Последние 50','Latest 50'),
 'all_available':('Все доступные','All available'), 'paste':('Вставить','Paste'),
 'link_accessible':('Ссылка для скачивания','Download link'),
 'add':('Добавить в очередь','Add to queue'), 'add_primary':('↓  Добавить в очередь','↓  Add to queue'),
 'download_options':('Параметры загрузки','Download options'),
 'audio_format':('MP3 — только звук','MP3 — audio only'),
 'all_media':('Все фото и видео','Photos and videos'), 'video_only':('Только видео','Videos only'), 'photo_only':('Только фото','Photos only'),
 'video_format':('Формат видео','Video format'), 'quality':('Качество','Quality'), 'content':('Содержимое','Content'),
 'author_folder':('Папка автора','Author folder'), 'post_folder':('Папка каждого поста','Folder per post'),
 'description_beside':('Описание рядом с файлом','Save description'), 'folder':('Папка','Folder'),
 'download_folder':('Папка загрузок','Download folder'), 'choose':('Выбрать…','Choose…'),
 'recent':('Недавние','Recent'), 'auto_start':('Автозапуск','Auto-start'),
 'single_post':('Один пост','Single post'), 'single_video':('Одно видео','Single video'),
 'batch':('Несколько ссылок','Multiple links'), 'profile':('Профиль','Profile'),
 'playlist':('Плейлист','Playlist'), 'lesson_player':('Урок / плеер','Lesson / player'),
 'profile_note':('Каждый пост — в отдельной папке. Список может потребовать полного обхода профиля.','Each post gets its own folder. Building the list may require scanning the full profile.'),
 'link_placeholder':('Вставьте ссылку на видео, публикацию или урок','Paste a video, post or lesson link'),
 'check_folder':('Проверьте папку загрузок.','Check the download folder.'),
 'photo_summary':('Фото · Исходный формат','Photos · Original format'),
 'audio_summary':('MP3 · Лучший доступный звук','MP3 · Best available audio'),
 'quality_cap':('до {height}p','up to {height}p'), 'best_quality':('Лучшее качество','Best quality'),
 'choose_profile':('Для этой ссылки выберите режим «Профиль».','Choose Profile mode for this link.'),
 'choose_playlist':('Для этой ссылки выберите режим «Плейлист».','Choose Playlist mode for this link.'),
 'quality_pending':('Проверка доступного качества… Добавление в очередь доступно.','Checking available quality… You can still add to the queue.'),
 'probe_cancelled':('Проверка остановлена при запуске загрузки. Добавление в очередь доступно.','Quality check stopped to start a download. You can still add to the queue.'),
 'probe_unavailable':('Проверка временно недоступна. Можно добавить в очередь.','Quality check is unavailable. You can still add to the queue.'),
 'best_selected':('Выбрано лучшее доступное качество.','Best available quality is selected.'),
 'quality_per_item':('Качество определяется для каждого материала при скачивании.','Quality is selected for each item when downloading.'),
 'best_available':('Лучшее доступное','Best available'), 'quality_limit':('До {height}p (предел)','Up to {height}p (limit)'),
 'batch_title':('Добавить несколько ссылок','Add multiple links'),
 'batch_help':('Одна ссылка на строку. YouTube, Instagram и GetCourse можно смешивать.','One link per line. Mix YouTube, Instagram and GetCourse.'),
 'for_profiles':('Для профилей Instagram','For Instagram profiles'),
 'cancel':('Отмена','Cancel'), 'ok':('ОК','OK'),
 'batch_summary':('Готово: {ready} · Неверных: {invalid} · Повторов: {duplicates} · Уже в списке: {existing}','Ready: {ready} · Invalid: {invalid} · Duplicates: {duplicates} · In queue: {existing}'),
 'bad_line':('Строка {line}: неподдерживаемая или неверная ссылка.','Line {line}: unsupported or invalid link.'),
 'duplicate_line':('Строка {line}: повтор ссылки.','Line {line}: duplicate link.'),
 'material':('Материал','Material'), 'parameters':('Параметры','Options'),
 'lesson_video':('Урок / видео','Lesson / video'), 'already_listed':('Уже в списке','Already in queue'),
 'best_audio':('Лучший доступный звук','Best available audio'), 'photo':('Фото','Photos'),
 'original_format':('Исходный формат','Original format'), 'description':('Описание {format}','Description {format}'),
 'latest_count':('Последние {count}','Latest {count}'), 'all_posts':('Все доступные посты','All available posts'),
 'select_lesson':('Выберите видео урока','Choose lesson videos'),
 'select_materials':('Какие материалы добавить в очередь?','Which items should be added to the queue?'),
 'video_number':('Видео {number}','Video {number}'), 'restore_source':('Восстановить источник','Restore source'),
 'original_link':('Вставьте исходную ссылку этого задания:','Paste the original link for this job:'),
 'new_download':('Новая загрузка','New download'),
 'state_queued':('В очереди','Queued'), 'state_probing':('Проверка ссылки','Checking link'),
 'state_downloading':('Скачивание','Downloading'), 'state_processing':('Обработка','Processing'),
 'state_completed':('Готово','Completed'), 'state_paused':('На паузе','Paused'),
 'state_failed':('Не удалось скачать','Download failed'), 'state_cancelled':('Отменено','Cancelled'),
 'source_needed':('Нужна ссылка','Link required'), 'selection_needed':('Выберите видео','Choose videos'),
 'instagram_wait':('Ожидание Instagram','Waiting for Instagram'), 'mb':('МБ','MB'), 'mb_s':('МБ/с','MB/s'),
 'menu_downloads':('Загрузки','Downloads'), 'menu_edit':('Правка','Edit'), 'menu_view':('Вид','View'),
 'menu_settings':('Настройки','Settings'), 'theme':('Тема','Theme'), 'language':('Язык','Language'),
 'dark':('Тёмная','Dark'), 'light':('Светлая','Light'), 'system':('Системная','System'),
 'undo':('Отменить ввод','Undo'), 'redo':('Повторить ввод','Redo'), 'cut':('Вырезать','Cut'),
 'copy':('Копировать','Copy'), 'delete':('Удалить','Delete'), 'select_all':('Выделить всё','Select all'),
 'error.invalid_link':('Проверьте ссылку и выбранный режим.','Check the link and selected mode.'),
 'error.already_queued':('Эта загрузка уже есть в списке.','This download is already in the queue.'),
 'error.invalid_folder':('Укажите папку для скачивания.','Choose a download folder.'),
 'error.folder_missing':('Папка недоступна. Проверьте путь.','Folder unavailable. Check the path.'),
 'error.storage_busy':('Хранилище занято. Повторите действие позже.','Storage is busy. Try again later.'),
 'error.storage_read_only':('Нет доступа для записи в папку данных ClipFlow.','Cannot write to the ClipFlow data folder.'),
 'error.queue_update_failed':('Не удалось сохранить очередь. Загрузки остановлены.','Could not save the queue. Downloads have been stopped.'),
 'error.source_changed':('Ссылка отличается от исходной. Добавьте её как новое задание.','The link differs from the original. Add it as a new job.'),
 'error.cooldown_active':('Срок ожидания ещё не истёк. Повторите позже.','The waiting period has not ended. Try again later.'),
 'error.settings_reset':('Повреждённые настройки сохранены в резервной копии. Восстановлены начальные параметры.','Damaged settings were backed up. Defaults have been restored.'),
 'error.legacy_settings_reset':('Старые настройки не удалось прочитать. Восстановлены начальные параметры.','Could not read old settings. Defaults have been restored.'),
 'error.app_closed':('Очередь закрыта. Перезапустите приложение.','The queue is closed. Restart the app.'),
 'error.generic':('Не удалось выполнить действие. Проверьте доступ и повторите попытку.','Action failed. Check access and try again.'),
 'error.queue_corrupt':('Файл очереди повреждён. Исходный файл сохранён; восстановите его из резервной копии.','The queue file is damaged. The original was preserved; restore a backup.'),
 'error.unsupported_queue_schema':('Данные очереди созданы другой версией ClipFlow. Используйте совместимую версию.','Queue data was created by a different ClipFlow version. Use a compatible version.'),
 'error.unsupported_settings_schema':('Настройки созданы другой версией ClipFlow. Используйте совместимую версию.','Settings were created by a different ClipFlow version. Use a compatible version.'),
}
CATALOG={language:{key:pair[index] for key,pair in MESSAGES.items()} for index,language in enumerate(('ru','en'))}


class Translator(QObject):
    changed=Signal()
    def __init__(self,language='ru',parent=None):
        super().__init__(parent); self.language=language; self._bindings=[]; self._qt=None
        if language not in CATALOG: raise ValueError('invalid_language')

    def text(self,key,**args): return CATALOG[self.language][key].format(**args)

    def bind(self,widget,key,setter='setText',**args):
        self._bindings.append((weakref.ref(widget),key,setter,args))
        getattr(widget,setter)(self.text(key,**args)); return widget

    def widget(self,factory,key,**args): return self.bind(factory(),key,**args)

    def set_language(self,language):
        if language not in CATALOG: raise ValueError('invalid_language')
        if self.language==language: return
        self.language=language
        live=[]
        for ref,key,setter,args in self._bindings:
            widget=ref()
            if widget is None: continue
            try: getattr(widget,setter)(self.text(key,**args)); live.append((ref,key,setter,args))
            except RuntimeError: pass  # Deleted Qt wrappers are not retained by a language catalogue.
        self._bindings=live; self.install_qt(); self.changed.emit()

    def install_qt(self):
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance()
        if self._qt is not None: app.removeTranslator(self._qt)
        self._qt=QTranslator(self)
        if self._qt.load(QLocale(self.language),'qtbase','_',QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
            app.installTranslator(self._qt)

    def close(self):
        from PySide6.QtWidgets import QApplication
        if self._qt is not None:
            QApplication.instance().removeTranslator(self._qt); self._qt=None
