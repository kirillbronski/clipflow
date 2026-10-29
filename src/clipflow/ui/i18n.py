"""Explicit RU/EN message catalogue; never translate user content by replacement."""
import weakref
from PySide6.QtCore import QObject,Signal,QLibraryInfo,QLocale,QTranslator

MESSAGES={
 'download_label':('Скачать','Download'),
 'sources_label':('И С Т О Ч Н И К И','S O U R C E S'),
 'filter_all':('Все','All'), 'filter_active':('В работе','Active'),
 'filter_completed':('Готово','Done'), 'filter_failed':('Ошибки','Errors'),
 'instagram_link':('Ссылка на пост или Reel Instagram','Instagram post or Reel link'),
 'instagram_hint':('Карусель целиком — по одной ссылке. Фото и видео сохранятся в исходном порядке.','One link downloads the whole carousel. Photos and videos keep their original order.'),
 'youtube_hint':('Видео, треки и плейлисты YouTube Music — в вашу коллекцию.','Videos, tracks and YouTube Music playlists — in your collection.'),
 'getcourse_hint':('Скачиваются только материалы, к которым у вас есть доступ.','Download materials you have access to.'),
 'instagram_subtitle':('Посты, Reels и карусели — в вашей коллекции.','Posts, Reels and carousels — in your collection.'),
 'youtube_subtitle':('Видео и музыка — в удобном формате на вашем компьютере.','Videos and music — in the format you need, on your computer.'),
 'getcourse_subtitle':('Уроки и материалы — для просмотра в удобное время.','Lessons and course materials — ready when you are.'),
 'history_count':('История  ·  {count}','History  ·  {count}'),
 'open_folder':('Открыть папку файла','Open file folder'),
 'clear_queue':('Очистить очередь (файлы останутся)','Clear queue (keep files)'),
 'clear_history':('Очистить историю (файлы останутся)','Clear history (keep files)'),
 'repeat_job':('Скачать повторно','Download again'),
 'remove_list':('Убрать из списка','Remove from list'),
 'delete_files':('Удалить файлы с диска','Delete files from disk'),
 'delete_confirmation':('Удалить записанные файлы ({count}) с диска? Это действие нельзя отменить. История останется.','Delete recorded files ({count}) from disk? This cannot be undone. History will remain.'),
 'files_missing':('Файлы отсутствуют','Files missing'),
 'error.files_missing':('Файлы удалены или перемещены. Можно скачать повторно.','Files were deleted or moved. You can download again.'),
 'error.unsafe_result_path':('Удаление отменено: файл находится вне исходной папки загрузки или путь изменился.','Deletion cancelled: a file is outside the original download folder or its path changed.'),
 'error.job_busy':('Дождитесь завершения активной загрузки перед этим действием.','Wait for the active download to finish before this action.'),
 'error.file_delete_failed':('Не удалось удалить все файлы. Проверьте права доступа и повторите.','Some files could not be deleted. Check access permissions and try again.'),
 'all_downloads':('Все загрузки','All downloads'), 'history':('История','History'),
 'local_note':('Файлы остаются\nна этом компьютере','Files stay\non this computer'),
 'batch_button':('+  Несколько ссылок','+  Multiple links'),
 'subtitle':('Все сервисы. Одна понятная очередь.','All services. One clear queue.'),
 'cancel_queue':('Отменить очередь','Cancel queue'),
 'clear_all':('Очистить всё','Clear all'),
 'clear_all_confirmation':('Остановить загрузки и убрать все задания ({count}) из очереди и истории всех площадок? Файлы останутся, если не включить удаление ниже.','Stop downloads and remove all {count} jobs from the queue and history for every service? Files stay unless deletion is selected below.'),
 'clear_all_delete_files':('Также удалить скачанные файлы с диска (необратимо)','Also delete downloaded files from disk (permanent)'),
 'start_queue':('▷  Запустить очередь','▷  Start queue'),
 'empty':('Здесь пока нет заданий. Добавьте первую ссылку.','No downloads yet. Add your first link.'),
 'footer':('Файлы сохраняются локально  ·  ClipFlow 2.0','Files are saved locally  ·  ClipFlow 2.0'),
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
MESSAGES.update({
 'accounts':('Аккаунты','Accounts'), 'about':('О программе','About'),
 'accounts_note':('Сессии защищены для этого пользователя компьютера. Вход открывается в отдельном окне ClipFlow.','Sessions are protected for this computer user. Sign-in opens in a separate ClipFlow window.'),
 'sign_in':('Войти','Sign in'), 'sign_out':('Выйти','Sign out'), 'configure_access':('Настроить доступ','Configure access'),
 'not_signed_in':('Вход не выполнен','Not signed in'), 'session_saved':('Сессия сохранена','Session saved'),
 'account_configured':('Профиль сохранён для выбранной школы','Profile saved for the selected school'),
 'school_lesson_url':('Ссылка на урок вашей школы','Your school lesson link'), 'access_method':('Способ доступа','Access method'),
 'email':('Email','Email'), 'password':('Пароль','Password'), 'cookies_file':('Файл cookies','Cookies file'), 'browser':('Браузер','Browser'),
 'auth_email':('Email и пароль','Email and password'), 'auth_cookies':('Файл cookies Netscape','Netscape cookies file'), 'auth_browser':('Сессия браузера','Browser session'),
 'school_scope_note':('Доступ применяется только к школе из этой ссылки. Для браузера: войдите в школу и закройте браузер перед чтением сессии. Старый профиль импортируется только после явного выбора школы.','Access applies only to the school in this link. For browser access, sign into the school and close the browser before reading its session. Importing an old profile requires explicitly selecting a school.'),
 'import_old_profile':('Импортировать прежний профиль','Import previous profile'), 'save':('Сохранить','Save'),
 'about_description':('Видео, аудио и фотографии сохраняются локально. YouTube, Instagram и GetCourse. Доступ к материалам зависит от сервиса и вашего аккаунта.','Save videos, audio and photos locally. YouTube, Instagram and GetCourse. Access depends on the service and your account.'),
 'auth_window_title':('Вход в {service} · ClipFlow','{service} sign-in · ClipFlow'),
 'auth_embedded_note':('Введите данные на странице сервиса, затем откройте сервис и сохраните сессию. Сохранённая сессия будет доступна после перезапуска ClipFlow.','Enter your details on the provider page, then open the service and save the session. The saved session remains available after restarting ClipFlow.'),
 'auth_native_mode':('Обычный Qt WebEngine','Standard Qt WebEngine'), 'auth_ipad51':('Chrome на iPad · 51','Chrome on iPad · 51'), 'auth_ipad87':('Chrome на iPad · 87','Chrome on iPad · 87'),
 'open_service':('Открыть сервис','Open service'), 'save_session':('Сохранить сессию','Save session'),
 'auth_page_ready':('Страница загружена','Page loaded'), 'auth_page_failed':('Не удалось загрузить страницу','Page did not load'),
 'auth_session_missing':('Сессия ещё не обнаружена. Откройте сервис после входа.','Session not detected yet. Open the service after signing in.'),
 'error.auth_invalid_settings':('Проверьте школу, способ доступа и заполненные поля.','Check the school, access method and required fields.'),
 'error.auth_invalid_school':('Вставьте ссылку на урок выбранной школы GetCourse.','Paste a lesson link from your chosen GetCourse school.'),
 'error.auth_storage_failed':('Не удалось сохранить защищённый профиль.','Could not save the protected profile.'),
 'error.auth_required':('Сохранённый вход недоступен. Откройте «Аккаунты» и войдите заново.','Saved sign-in is unavailable. Open Accounts and sign in again.'),
 'error.auth_launch_failed':('Не удалось открыть окно входа.','Could not open the sign-in window.'),
 'error.auth_scope_mismatch':('Этот профиль не относится к выбранному сервису или школе.','This profile belongs to another service or school.'),
})
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
