import sys
from platform_support import RESOURCE_DIR, APP_DATA, AUTH_DIR, SETTINGS_DIR, platform_text, FONT_FAMILY, MODIFIER, CONTEXT_BUTTON, IS_MAC, binary_path, open_folder as reveal_folder, protect_profile, atomic_redraw, clipboard_text
from download_events import coalesce_updates
if __name__ == '__main__' and any(flag in sys.argv for flag in ('--youtube-login','--instagram-login','--auth-self-test','--instagram-auth-self-test')):
    from embedded_auth import main
    raise SystemExit(main())

import json
import os
import queue
import re
import shutil
import sys
import threading
import time
import base64
import ctypes
from contextlib import contextmanager
from html.parser import HTMLParser
from youtube_session import YouTubeSession
from instagram_session import InstagramSession
from instagram_profile import profile_username, profile_posts
from media_names import short_media_title
from instagram_media import ClipFlowInstagramIE, is_instagram_url, media_title, download_photo, save_description, author_directory, post_directory
from pathlib import Path
from urllib.parse import urlparse
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import yt_dlp
from version import APP_VERSION
PROGRESS_TRANSLATIONS = {'Отменяю…': 'Cancelling…', 'Открываю встроенное окно входа YouTube…': 'Opening embedded YouTube sign-in…', 'Скачивание…': 'Downloading…', 'Получаю информацию…': 'Fetching information…', 'Файл ': 'File ', 'файлов': 'files'}
BROWSER_TRANSLATIONS = {'Браузер для входа': 'Sign-in browser', 'Открыть браузер': 'Open browser',
    'По умолчанию': 'Default browser',
    'Safari на iPad · экспериментальный режим': 'Safari on iPad · experimental mode',
    'Меняется только User-Agent окна входа. Google может отклонить вход.': 'Only the sign-in window User-Agent changes. Google may reject sign-in.'}
TRANSLATIONS = {'+ В очередь': '+ Add to queue', 'Email и пароль': 'Email and password', 'Без входа': 'No sign-in', 'В очереди': 'Queued', 'Ваши видео. В вашей папке.': 'Your videos. Your folder.', 'Видео': 'Video', 'Видео MP4': 'MP4 video', 'Видео — MP4': 'MP4 video', 'Все видео урока': 'All lesson videos', 'Все файлы': 'All files', 'Вставить': 'Paste', 'Вход подтверждён: ': 'Signed in: ', 'Выберите вкладку': 'Select a tab', 'Выберите папку': 'Select a folder', 'Выбор видео урока': 'Select lesson videos', 'Выбрать видео': 'Select videos', 'Выбрать…': 'Browse…', 'Выбрать': 'Browse', 'Выделить всё': 'Select all', 'Выйти': 'Sign out', 'Вырезать': 'Cut', 'Готово: ': 'Done: ', 'ДОСТУП К УРОКУ': 'LESSON ACCESS', 'Доступ GetCourse': 'GetCourse access', 'Доступ к закрытым урокам': 'Access to private lessons', 'Доступ: ': 'Access: ', 'Завершено: скачано ': 'Completed: downloaded ', 'Загрузка завершена': 'Download complete', 'Загрузки': 'Downloads', 'Звук MP3': 'MP3 audio', 'Идёт скачивание': 'Download in progress', 'КАЧЕСТВО': 'QUALITY', 'Какие видео скачать?': 'Which videos would you like to download?', 'Копировать': 'Copy', 'Лучшее доступное': 'Best available', 'Настроить доступ': 'Configure access', 'Не найден FFmpeg': 'FFmpeg not found', 'Не удалось выйти': 'Could not sign out', 'Не удалось открыть папку': 'Could not open folder', 'Не удалось скачать': 'Download failed', 'Недавние': 'Recent folders', 'Недоступное видео': 'Unavailable video', 'ОБЪЁМ ЗАГРУЗКИ': 'DOWNLOAD SCOPE', 'Обработка файла…': 'Processing file…', 'Одно видео YouTube': 'One YouTube video', 'Открыть папку': 'Open folder', 'Отмена': 'Cancel', 'Отменено': 'Cancelled', 'Отменить': 'Cancel download', 'Ошибка скачивания': 'Download error', 'Папка для скачивания': 'Download folder', 'Папка': 'Folder', 'Пароль GetCourse': 'GetCourse password', 'Первое видео': 'First video', 'Плейлист YouTube целиком': 'Entire YouTube playlist', 'Плейлист YouTube': 'YouTube playlist', 'Плейлист': 'Playlist', 'Пока нет загрузок': 'No downloads yet', 'Получаю видео: ': 'Fetching video: ', 'Получаю видео…': 'Fetching video…', 'Получаю название видео…': 'Fetching video title…', 'Понятно': 'OK', 'Применить': 'Apply', 'Проверьте ссылку': 'Check the link', 'Профиль GetCourse не сохранён': 'No saved GetCourse profile', 'Профиль не сохранён': 'Profile was not saved', 'Скачано': 'Downloaded', 'Скачать выбранные': 'Download selected', 'Скачать с GetCourse': 'Download from GetCourse', 'Скачать с YouTube': 'Download from YouTube', 'Скачивание отменено': 'Download cancelled', 'Сохранён профиль: ': 'Saved profile: ', 'Ссылка на видео или плейлист YouTube': 'YouTube video or playlist link', 'Ссылка на урок или плеер GetCourse': 'GetCourse lesson or player link', 'Только звук — MP3': 'Audio only — MP3', 'Урок GetCourse': 'GetCourse lesson', 'ФОРМАТ': 'FORMAT', 'Файл cookies · формат Netscape': 'Cookies file · Netscape format', 'Файл cookies': 'Cookies file', 'Часть видео недоступна': 'Some videos are unavailable', 'Яндекс Браузер': 'Yandex Browser', 'Вставить ссылку': '＋  Paste link', 'Настройки': 'Settings', 'Язык интерфейса': 'Interface language', 'О программе': 'About', 'Русский': 'Russian', 'Видео и плейлисты YouTube, уроки GetCourse.': 'YouTube videos and playlists, GetCourse lessons.', 'Версия ': 'Version ', 'Защита сохранённого профиля: macOS Keychain.': 'Saved profile protection: macOS Keychain.', ' видео в очереди': ' videos queued', ' ожидают · ': ' waiting · ', ' в списке': ' in list', ' из ': ' of ', ' с ошибками': ' failed', ' скачано · ': ' downloaded · ', '. Ошибок: ': '. Errors: ', ' МБ/с': ' MB/s', ' — YouTube и GetCourse': ' — YouTube and GetCourse', ' — Видео ': ' — Video ', ' видео': ' videos', 'Видео ': 'Video ', 'В буфере обмена нет текста. Скопируйте ссылку.': 'The clipboard has no text. Copy a link first.', 'Буфер обмена пуст. Сначала скопируйте ссылку.': 'The clipboard is empty. Copy a link first.', 'Введите email и пароль GetCourse.': 'Enter your GetCourse email and password.', 'Вставьте ссылку YouTube, GetCourse или публикации Instagram.': 'Paste a full YouTube, GetCourse lesson or GetCourse player link.', 'Вставьте ссылку, выберите параметры и нажмите «Скачать».': 'Paste a link, choose options, then click Download.', 'Вставьте ссылку на видео или плейлист.\nКачество, формат и папка — на панели выше.': 'Paste a video or playlist link.\nChoose quality, format and folder in the panel above.', 'Выберите существующий файл cookies.': 'Select an existing cookies file.', 'Для закрытого урока настройте доступ.': 'Configure access for a private lesson.', 'Запускайте программу из полной папки приложения.': 'Run the app from its complete application folder.', 'На странице нет доступного видео. Проверьте вход GetCourse.': 'No video is available on this page. Check your GetCourse sign-in.', 'На странице нет доступных видео.': 'No videos are available on this page.', 'Не удалось скачать. Проверьте ссылку, доступ или подключение.': 'Download failed. Check the link, access and connection.', 'Выберите вкладку платформы из ссылки: YouTube, GetCourse или Instagram.': 'Use the YouTube tab for YouTube or the GetCourse tab for GetCourse lessons.', 'Отменено. Повторный запуск продолжит частичные файлы и пропустит готовые.': 'Cancelled. Restarting resumes partial files and skips completed downloads.', 'Отменяю загрузку. Текущая обработка файла может сначала завершиться.': 'Cancelling the download. Current file processing may finish first.', 'Плейлист пуст, закрыт или недоступен.': 'The playlist is empty, private or unavailable.', 'Сначала выберите существующую папку.': 'Select an existing folder first.', 'Сначала дождитесь завершения или нажмите «Отменить».': 'Wait for the download to finish or click Cancel download.', 'Ссылка вставлена. Выберите параметры и нажмите «Скачать».': 'Link pasted. Choose options, then click Download.', 'Укажите папку для скачивания.': 'Choose a download folder.', 'Урок доступен только после входа в аккаунт школы.': 'Sign in to your school account to access this lesson.', 'GetCourse отклонил вход. Проверьте email и пароль аккаунта этой школы.': 'GetCourse rejected the sign-in. Check your email and password for this school.', 'Все доступные видео плейлиста · отдельная папка · номера по порядку': 'All available playlist videos · separate folder · sequential numbering', 'Одно видео YouTube или первое видео урока GetCourse': 'One YouTube video or the first GetCourse lesson video', 'Откройте урок в ': 'Open the lesson in ', 'Не удалось прочитать сохранённый вход из ': 'Could not read the saved session from ', ': файл сессии занят браузером.\n\nЗакройте все окна ': ': the session file is locked by the browser.\n\nClose all windows of ', ' защитил сохранённую сессию, и программе не удалось её прочитать.': ' protected its saved session and the app could not read it.', 'Нужна ссылка с параметром list=…\nДля одного видео или GetCourse выключите переключатель плейлиста.': 'A link with a list=… parameter is required.\nDisable playlist mode for a single video or GetCourse.', 'Профиль сохраняется с защитой macOS Keychain для этого пользователя.\nКнопка «Выйти» удаляет сохранённые данные из программы.': 'The profile is protected by macOS Keychain for this user.\nSign out removes the saved credentials from the app.', 'Введите email и пароль от аккаунта вашей школы GetCourse.\nПрограмма войдёт в школу из ссылки на урок.\nВставка: ⌘+V, Shift+Insert или правая кнопка мыши.\nДанные сохраняются с защитой macOS Keychain.': 'Enter the email and password for your GetCourse school account.\nThe app signs in to the school from the lesson link.\nPaste using ⌘+V, Shift+Insert or the right-click menu.\nCredentials are saved with macOS Keychain protection.', 'Выберите экспорт cookies в формате Netscape из браузера,\nв котором вы вошли в школу и открыли урок.\nПрограмма использует сохранённый вход из этого файла.\nИсходный файл не изменяется.': 'Select a Netscape cookies export from the browser\nwhere you signed in to your school and opened the lesson.\nThe app uses the saved session from this file.\nThe original file is not changed.', 'Подходит для открытых уроков и прямых ссылок на плеер.\nДля закрытого урока выберите браузер, email и пароль\nили файл cookies.\nВход должен давать доступ к этому уроку.': 'Use this for public lessons and direct player links.\nFor a private lesson, select a browser, email and password\nor a cookies file.\nYour account must have access to the lesson.', ' и войдите в аккаунт школы.\nЗатем полностью закройте браузер, нажмите «Применить» и скачайте урок.\nПрограмма прочитает сохранённый вход из профиля браузера.\nЕсли чтение не удаётся, выберите email и пароль или файл cookies.': ' and sign in to your school account.\nCompletely close the browser, click Apply and download the lesson.\nThe app reads the saved session from the browser profile.\nIf this fails, use email and password or a cookies file.', '\n\nПроверьте доступ к уроку в этой школе. Вход по email использует аккаунт школы из ссылки на урок.': '\n\nCheck that your account has access to this school lesson. Email sign-in uses the school from the lesson link.', '. Если он продолжает работать в фоне, завершите его через значок в области уведомлений или отключите фоновую работу в настройках браузера. Затем повторите скачивание.\n\nМожно также выбрать «Email и пароль» — этот способ не требует закрывать браузер.': '. If it keeps running in the background, exit it from the system tray or disable background operation in browser settings. Then retry.\n\nYou can also use Email and password without closing the browser.', '\n\nВыберите «Email и пароль» либо экспортируйте cookies своей школы в формате Netscape и выберите «Файл cookies».': '\n\nUse Email and password, or export your school cookies in Netscape format and select Cookies file.'}
TRANSLATIONS.update({'Сохранять описание': 'Save description', 'Видео недоступно': 'Video unavailable', 'Вход в школу GetCourse': 'Signing in to GetCourse', 'Проверяю качество…': 'Checking quality…', 'Качество проверено': 'Quality checked', 'Нет вариантов качества': 'No quality options', 'Не удалось проверить качество': 'Could not check quality', 'Скачать с Instagram': 'Download from Instagram'})
TRANSLATIONS.update({'Доскачать': 'Resume', 'Пауза': 'Pause', 'Продолжить': 'Continue', 'На паузе': 'Paused', 'Приостанавливаю загрузку…': 'Pausing download…', 'Эта загрузка уже в очереди.': 'This download is already queued.', 'Этот файл уже скачан.': 'This file has already been downloaded.', ' скачивается · ': ' downloading · ', ' ожидают': ' waiting'})
TRANSLATIONS.update({
    'Для автоматического входа выберите браузером по умолчанию Chrome, Edge, Brave, Opera, Vivaldi или Яндекс Браузер.': 'For automatic sign-in, set Chrome, Edge, Brave, Opera, Vivaldi or Yandex Browser as your default browser.',
    'Войти в YouTube': 'Sign in to YouTube', 'Вход YouTube': 'YouTube sign-in',
    'YouTube: вход не выполнен': 'YouTube: not signed in',
    'YouTube: сессия сохранена': 'YouTube: session saved',
    'Подтвердить вход': 'Confirm sign-in',
    'Войдите на YouTube в отдельном окне браузера.\nЗатем нажмите «Подтвердить вход».\nПрофиль и защищённая сессия сохраняются между запусками.':
        'Sign in to YouTube in the separate browser window.\nThen click Confirm sign-in.\nThe profile and protected session persist across app restarts.',
    'Открываю окно входа…': 'Opening sign-in window…',
    'Окно входа открыто. Войдите в аккаунт на YouTube.': 'Sign-in window opened. Sign in to your YouTube account.',
    'Проверяю вход…': 'Checking sign-in…',
    'Сначала войдите в аккаунт на YouTube в открывшемся окне.': 'First sign in to YouTube in the browser window.',
    'Не удалось прочитать сессию окна входа.': 'Could not read the sign-in window session.',
    'Сессия YouTube недоступна. Нажмите «Войти в YouTube» и подтвердите вход.': 'YouTube session unavailable. Click Sign in to YouTube and confirm sign-in.',
    'Установите Google Chrome или Microsoft Edge для входа в YouTube.': 'Install Google Chrome or Microsoft Edge to sign in to YouTube.',
    'Не удалось открыть окно входа. Закройте прежнее окно входа ClipFlow и повторите.': 'Could not open the sign-in window. Close the previous ClipFlow sign-in window and retry.',
})
TRANSLATIONS.update({'Очистить список': 'Clear list', 'Удалить файл': 'Delete file', 'Удаление файлов': 'Delete files', 'Удалить': 'Delete', 'Файл удалён': 'File deleted', 'Удалить эти файлы с диска? Это действие нельзя отменить.': 'Delete these files from disk? This action cannot be undone.', 'Дождитесь завершения текущей задачи.': 'Wait for the current task to finish.', 'Не удалось удалить файл': 'Could not delete file'})
TRANSLATIONS.update({'Действия': 'Actions', 'Удалить все файлы': 'Delete all files'})
UI_LANGUAGE = 'ru'


def ui_text(text):
    return TRANSLATIONS.get(text, text) if UI_LANGUAGE == 'en' else text


TRANSLATIONS = {platform_text(k): platform_text(v) for k, v in TRANSLATIONS.items()}

from yt_dlp.extractor.getcourseru import GetCourseRuPlayerIE, GetCourseRuIE
from yt_dlp.utils import ExtractorError, urlencode_postdata


GETCOURSE_PLAYER = r'https?://(?:player02\.getcourse\.ru|[a-zA-Z0-9-]+\.vhcdn\.com|[a-zA-Z0-9-]+\.gceuproxy\.com)/sign-player/?\?(?:[^#]+&)?json=[^#&]+'
# GetCourse now serves the same player through regional gceuproxy hosts.
GetCourseRuPlayerIE._VALID_URL = GETCOURSE_PLAYER
GetCourseRuPlayerIE._EMBED_REGEX = [rf'<iframe[^>]+\bsrc=[\'"](?P<url>{GETCOURSE_PLAYER}[^\'"]*)']


def getcourse_login(self, hostname, username, password):
    login_url = f'https://{hostname}{self._LOGIN_URL_PATH}'
    webpage = self._download_webpage(login_url, None)
    # The school signs its own page timestamp; local wall-clock time is invalid.
    payload = {
        'action': 'processXdget',
        'xdgetId': self._html_search_regex(
            r'<form[^>]+\bclass="[^"]*\bstate-login[^"]*"[^>]+\bdata-xdget-id="([^"]+)"', webpage, 'xdgetId'),
        'params[action]': 'login', 'params[url]': login_url,
        'params[object_type]': 'cms_page', 'params[object_id]': -1,
        'params[email]': username, 'params[password]': password,
        'requestTime': self._search_regex(r'window\.requestTime\s*=\s*[\'"]?(\d+)', webpage, 'request time'),
        'requestSimpleSign': self._search_regex(r'window\.requestSimpleSign\s*=\s*[\'"]([\da-f]+)', webpage, 'simple sign'),
    }
    response = self._download_json(login_url, None, 'Вход в школу GetCourse',
        data=urlencode_postdata(payload), headers={'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Origin': f'https://{hostname}', 'Referer': login_url, 'X-Requested-With': 'XMLHttpRequest'})
    if isinstance(response, dict):
        result = response.get('data') if isinstance(response.get('data'), dict) else response
        if result.get('errorMessage') or result.get('success') is False:
            raise ExtractorError('GetCourse отклонил вход. Проверьте email и пароль аккаунта этой школы.', expected=True)


GetCourseRuIE._login = getcourse_login


class LessonTitleParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.parts = {'title': [], 'description': []}

    def handle_starttag(self, tag, attrs):
        classes = dict(attrs).get('class', '').split()
        role = next((key for key in self.parts if any(
            value == 'lesson-' + key or value == 'lesson-' + key + '-value' for value in classes)), None)
        self.stack.append((tag, role or (self.stack[-1][1] if self.stack else None)))
        if tag in ('br', 'hr', 'img', 'input', 'meta', 'link'):
            self.stack.pop()

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        if self.stack and self.stack[-1][1]:
            self.parts[self.stack[-1][1]].append(data)


def full_lesson_title(webpage, fallback):
    parser = LessonTitleParser()
    parser.feed(webpage)
    title = ' '.join(''.join(parser.parts['title']).split()) or fallback
    description = ' '.join(''.join(parser.parts['description']).split())
    return f'{title} — {description}' if description and description.casefold() not in title.casefold() else title


def getcourse_extract(self, url):
    hostname = urlparse(url).hostname
    username, password = self._get_login_info(netrc_machine=hostname)
    if username:
        self._login(hostname, username, password)
    display_id = self._match_id(url)
    webpage, handle = self._download_webpage_handle(url, display_id)
    if self._LOGIN_URL_PATH in handle.url:
        raise ExtractorError('Урок доступен только после входа в аккаунт школы.', expected=True)
    title = full_lesson_title(webpage, self._og_search_title(webpage, default=None) or self._html_extract_title(webpage))
    return self.playlist_from_matches(re.findall(GetCourseRuPlayerIE._EMBED_REGEX[0], webpage),
        self._search_regex(r'window\.(?:lessonId|gcsObjectId)\s*=\s*(\d+)', webpage, 'playlist id', default=display_id),
        title, display_id=display_id, ie=GetCourseRuPlayerIE,
        video_kwargs={'url_transparent': True, 'title': title})


GetCourseRuIE._real_extract = getcourse_extract


def clean_download_sidecars(info, ydl, folder):
    """Remove only resume files belonging to successfully completed media."""
    if not info:
        return
    if info.get('_type') == 'playlist':
        for entry in info.get('entries') or []:
            clean_download_sidecars(entry, ydl, folder)
        return
    candidates = [info.get('filepath'), info.get('_filename'), ydl.prepare_filename(info)]
    candidates += [item.get('filepath') for item in info.get('requested_downloads') or []]
    base = Path(folder).resolve()
    for value in candidates:
        if not value:
            continue
        path = Path(value).resolve()
        if not path.is_relative_to(base):
            continue
        sidecar = Path(str(path) + '.ytdl')
        if sidecar.is_file():
            try:
                sidecar.unlink()
            except OSError:
                pass


def completed_media_paths(info, ydl, folder):
    if not info:
        return []
    if info.get('_type') == 'playlist':
        return [path for entry in info.get('entries') or [] for path in completed_media_paths(entry, ydl, folder)]
    candidates = [info.get('filepath'), info.get('_filename'), ydl.prepare_filename(info)]
    candidates += [item.get('filepath') for item in info.get('requested_downloads') or []]
    candidates += list((info.get('__files_to_move') or {}).values())
    root = Path(folder).resolve()
    return sorted({str(path) for value in candidates if value for path in [Path(value).resolve()]
        if path.is_relative_to(root) and path.is_file() and path.suffix.lower() in ('.mp4', '.mp3', '.mkv', '.webm', '.m4a', '.opus', '.ogg', '.jpg', '.jpeg', '.png', '.webp', '.avif')})


def supported_url(url):
    parsed = urlparse(url)
    host = (parsed.hostname or '').lower()
    if parsed.scheme not in ('https', 'http') or parsed.username or parsed.password:
        return False
    return is_instagram_url(url) or bool(profile_username(url)) or host == 'youtu.be' or host == 'youtube.com' or host.endswith('.youtube.com') or host.endswith(('.getcourse.ru', '.getcourse.io')) or bool(re.match(GETCOURSE_PLAYER, url))


def needs_getcourse_login(url):
    return (urlparse(url).hostname or '').endswith(('.getcourse.ru', '.getcourse.io')) and '/sign-player' not in urlparse(url).path


QUALITY = {
    'Лучшее доступное': None,
    '2160p (4K)': 2160,
    '1440p': 1440,
    '1080p': 1080,
    '720p': 720,
    '480p': 480,
    '360p': 360,
}
TRANSLATIONS.update({'Скачать': 'Download', 'Добавить в очередь': 'Add to queue', 'Автоскачивание': 'Auto-download'})
BASE = RESOURCE_DIR
CONFIG = SETTINGS_DIR / 'settings.json'
PROFILE_FILE = CONFIG.with_name('getcourse-profile.dat')




BROWSERS = {'Google Chrome': 'chrome', 'Microsoft Edge': 'edge', 'Mozilla Firefox': 'firefox',
            'Opera': 'opera', 'Opera GX': 'opera', 'Яндекс Браузер': 'chrome',
            'Brave': 'brave', 'Vivaldi': 'vivaldi', 'Chromium': 'chromium', 'Whale': 'whale'}


def browser_cookie_source(name):
    if name == 'Яндекс Браузер':
        return ('chrome', str(Path.home() / 'Library/Application Support/Yandex/YandexBrowser' if IS_MAC else Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'Yandex/YandexBrowser/User Data'))
    if name == 'Opera GX':
        return ('opera', str(Path.home() / 'Library/Application Support/com.operasoftware.OperaGX' if IS_MAC else Path(os.environ.get('APPDATA', Path.home() / 'AppData/Roaming')) / 'Opera Software/Opera GX Stable'))
    return (BROWSERS[name],)


def access_error_message(error, access):
    text = str(error)
    method = (access or {}).get('method', 'Без входа')
    if method == 'YouTube session':
        return text + '\n\n' + 'Сессия YouTube недоступна. Нажмите «Войти в YouTube» и подтвердите вход.'
    if method in BROWSERS:
        lowered = text.lower()
        if 'could not copy' in lowered and 'cookie' in lowered:
            return (f'Не удалось прочитать сохранённый вход из {method}: файл сессии занят браузером.\n\n'
                    f'Закройте все окна {method}. Если он продолжает работать в фоне, '
                    'завершите его через значок в области уведомлений или отключите фоновую работу '
                    'в настройках браузера. Затем повторите скачивание.\n\n'
                    'Можно также выбрать «Email и пароль» — этот способ не требует закрывать браузер.')
        if 'decrypt' in lowered or 'dpapi' in lowered:
            return (f'{method} защитил сохранённую сессию, и программе не удалось её прочитать.\n\n'
                    'Выберите «Email и пароль» либо экспортируйте cookies своей школы '
                    'в формате Netscape и выберите «Файл cookies».')
    if method != 'Без входа':
        text += '\n\nПроверьте доступ к уроку в этой школе. Вход по email использует аккаунт школы из ссылки на урок.'
    return text


def default_download_folder():
    downloads = Path.home() / 'Downloads'
    if os.name == 'nt':
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders') as key:
                value, _ = winreg.QueryValueEx(key, '{374DE290-123F-4565-9164-39C4925E467B}')
                downloads = Path(os.path.expandvars(value))
        except OSError:
            pass
    return str(downloads / 'ClipFlow')


def download_options(folder, mode, quality, hook, access=None):
    ffmpeg = binary_path('ffmpeg')
    node = binary_path('node')
    options = {
        'paths': {'home': folder},
        'outtmpl': '%(title).56s.%(ext)s',
        'noplaylist': True,
        'windowsfilenames': True,
        'concurrent_fragment_downloads': 8,
        'progress_hooks': [hook],
        'postprocessor_hooks': [hook],
        'quiet': True,
        'no_warnings': True,
        'retries': 5,
        'socket_timeout': 30,
        'playlist_items': '1',
    }
    if ffmpeg:
        options['ffmpeg_location'] = ffmpeg
    if node:
        options['js_runtimes'] = {'node': {'path': str(node)}}
    if access:
        if access['method'] == 'YouTube session':
            options['_youtube_session'] = True
        elif access['method'] == 'Instagram session':
            options['_instagram_session'] = True
        elif access['method'] in BROWSERS:
            options['cookiesfrombrowser'] = browser_cookie_source(access['method'])
        elif access['method'] == 'Email и пароль':
            options.update(username=access['email'], password=access['password'])
        elif access['method'] == 'Файл cookies':
            # Load into memory so yt-dlp does not overwrite the user's export.
            options['_cookies_source'] = access['file']
    if mode == 'Только звук — MP3':
        options['format'] = 'bestaudio/best'
        options['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}]
    else:
        height = QUALITY[quality]
        limit = f'[height<={height}]' if height else ''
        options['format'] = f'bestvideo{limit}+bestaudio/best{limit}'
        container = {'Видео — MKV': 'mkv', 'Видео — WebM': 'webm'}.get(mode, 'mp4')
        options['merge_output_format'] = 'mkv' if container == 'webm' else container
        options['final_ext'] = container
        # Also convert single-stream downloads; merging alone does not set their container.
        options['postprocessors'] = [{'key': 'FFmpegVideoConvertor', 'preferedformat': container}]
        if container == 'webm':
            # Instagram/GetCourse may only offer H.264/AAC, which WebM cannot contain.
            options['postprocessor_args'] = {'videoconvertor+ffmpeg_o':
                ['-c:v', 'libvpx-vp9', '-crf', '32', '-b:v', '0', '-c:a', 'libopus']}
    return options


if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).parent / '_internal'))
import customtkinter as ctk
from PIL import Image
from urllib.parse import parse_qs

COLORS = {
    'background': '#141211', 'surface': '#211A19', 'surface_high': '#2D2422',
    'primary': '#FF0000', 'primary_action': '#D50000', 'primary_hover': '#B80000',
    'on_primary': '#FFFFFF', 'primary_container': '#930100', 'on_primary_container': '#FFDAD4',
    'secondary': '#E7BDB7', 'secondary_container': '#5D3F3B',
    'tertiary': '#E5C18D', 'text': '#F1DFDA', 'muted': '#D8C2BC',
    'outline': '#85736F', 'outline_variant': '#53433F', 'error': '#FFB4AB',
}
YOUTUBE_COLORS = COLORS.copy()
GETCOURSE_COLORS = dict(COLORS, background='#0D1619', surface='#162328', surface_high='#213239',
    primary='#013A4C', primary_action='#013A4C', primary_hover='#02546A',
    primary_container='#013A4C', on_primary_container='#D4F5F1', secondary='#A9D8D3',
    secondary_container='#284F53', tertiary='#35D3C9', text='#E0F0F1', muted='#B8CDCF',
    outline='#819B9F', outline_variant='#3C5258', secondary_hover='#35666A')
YOUTUBE_COLORS['secondary_hover'] = '#74524D'
COLORS.update(YOUTUBE_COLORS)
ctk.set_appearance_mode('dark')
ctk.set_default_color_theme('dark-blue')


def edit_key(event):
    # Tk reports layout-dependent keysyms; preserve physical editing keys in RU.
    key = event.keysym.lower()
    if not IS_MAC:
        key = {86: 'v', 67: 'c', 88: 'x', 65: 'a'}.get(event.keycode, key)
    return {'cyrillic_em': 'v', 'м': 'v', 'cyrillic_es': 'c', 'с': 'c',
            'cyrillic_che': 'x', 'ч': 'x', 'cyrillic_ef': 'a', 'ф': 'a'}.get(key, key)


class MaterialEntry(ctk.CTkEntry):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bind(f'<{MODIFIER}-KeyPress>', self.edit_shortcut)
        self.bind('<Shift-Insert>', self.paste_text)
        self.bind('<<Paste>>', self.paste_text)
        self.paste_callback = None
        self._edit_popup = None
        for sequence in ('<Button-2>', '<Button-3>') if IS_MAC else ('<Button-3>',):
            self.bind(sequence, self.edit_menu)
        if IS_MAC:
            self.bind('<Control-Button-1>', self.edit_menu)

    def paste_text(self, event=None):
        if self.paste_callback is not None:
            return self.paste_callback(event)
        if self.cget('state') == 'disabled':
            return 'break'
        try:
            text = clipboard_text(self)
        except tk.TclError:
            return 'break'
        if self.select_present():
            self.delete('sel.first', 'sel.last')
        self.insert('insert', text)
        return 'break'

    def edit_shortcut(self, event):
        key = edit_key(event)
        if key == 'v':
            return self.paste_text()
        if key == 'a':
            self.select_range(0, 'end')
            return 'break'
        if key in ('c', 'x'):
            self._entry.event_generate('<<Copy>>' if key == 'c' else '<<Cut>>')
            return 'break'

    def edit_menu(self, event):
        self.focus_set()
        if self._edit_popup is not None:
            self._edit_popup.destroy()
        menu = self._edit_popup = tk.Menu(self, tearoff=False)
        menu.add_command(label=ui_text('Вставить'), command=self.paste_text)
        menu.add_command(label=ui_text('Копировать'), command=lambda: self._entry.event_generate('<<Copy>>'))
        menu.add_command(label=ui_text('Вырезать'), command=lambda: self._entry.event_generate('<<Cut>>'))
        menu.add_command(label=ui_text('Выделить всё'), command=lambda: self.select_range(0, 'end'))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return 'break'

    def selection_range(self, start, end):
        self.select_range(start, end)

    def selection_present(self):
        return self.select_present()

    def event_generate(self, sequence, **kwargs):
        return self._entry.event_generate(sequence, **kwargs)


def youtube_playlist_url(url):
    parsed = urlparse(url)
    host = (parsed.hostname or '').lower()
    playlist_id = parse_qs(parsed.query).get('list', [''])[0]
    if not playlist_id or not (host == 'youtu.be' or host == 'youtube.com' or host.endswith('.youtube.com')):
        return None
    if not re.fullmatch(r'[A-Za-z0-9_-]+', playlist_id):
        return None
    return 'https://www.youtube.com/playlist?list=' + playlist_id


for palette in (COLORS, YOUTUBE_COLORS, GETCOURSE_COLORS):
    palette.update(background='#141416', surface='#1D1D20', surface_high='#28282D', outline_variant='#414149', outline='#85858F', text='#F2F2F5', muted='#B8B8C1')

TRANSLATIONS.update({'До 10 публикаций': 'Up to 10 posts', 'До 50 публикаций': 'Up to 50 posts', 'До 100 публикаций': 'Up to 100 posts', 'Все публикации': 'All posts', 'Получаю список публикаций…': 'Fetching posts…', 'Добавлено в очередь': 'Added to queue', 'Видео MKV': 'MKV video', 'Видео WebM': 'WebM video', 'Папка для каждого поста': 'Folder for each post', 'Видео урока': 'Lesson videos', 'Показывать завершённые': 'Show completed', 'Все': 'All', 'Активные': 'Active', 'Завершённые': 'Completed', 'Ошибки': 'Errors', 'Добавить': 'Add', 'Формат': 'Format', 'Качество': 'Quality', 'Аккаунт': 'Account', 'Вид': 'View', 'Аккаунты': 'Accounts', 'Справка': 'Help', 'Добавить ссылку': 'Add link', 'Добавить несколько ссылок': 'Add multiple links', 'Одна ссылка на строку': 'One link per line', 'Приостановить все': 'Pause all', 'Продолжить все': 'Resume all', 'Очистить завершённые': 'Clear completed', 'Компактный список': 'Compact list', 'Подробный список': 'Detailed list', 'Масштаб интерфейса': 'Interface scale', 'Общие': 'General', 'Скачивание': 'Downloads', 'Как пользоваться': 'Getting started', 'Горячие клавиши': 'Keyboard shortcuts', 'Журнал ошибок': 'Error log', 'О ClipFlow': 'About ClipFlow', 'Ошибок нет': 'No errors', 'Копировать название': 'Copy title', 'Повторить': 'Retry', 'Подробности': 'Details', 'Убрать из списка': 'Remove from list', 'Видео и аудио — в вашей коллекции.': 'Video and audio — in your collection.', 'История изменений': 'Release notes', 'Скопировать информацию для поддержки': 'Copy support information', 'Лицензии компонентов': 'Component licenses'})

INSTAGRAM_COLORS = dict(YOUTUBE_COLORS, primary='#E1306C', primary_action='#C13584', primary_hover='#A42A71', primary_container='#58203E', on_primary_container='#FFD9EB', secondary='#F4B4D4', secondary_container='#513049', secondary_hover='#6E3B60', tertiary='#F77737')
TRANSLATIONS.update({'Папка с ником автора': 'Folder by account username', 'Видео и фото (MP4)':'Video and photos (MP4)', 'Содержимое':'Content','Всё':'All media','Только видео':'Videos only','Только фото':'Photos only','Ссылка на публикацию или профиль Instagram':'Instagram post or profile link','Войти в Instagram':'Sign in to Instagram','Instagram: сессия сохранена':'Instagram: session saved','Instagram: вход не выполнен':'Instagram: not signed in','Открываю окно входа Instagram…':'Opening Instagram sign-in…'})


TRANSLATIONS['Вставьте ссылку на Reel или публикацию.\nСохраняйте видео, фото или всю карусель.'] = 'Paste a Reel or post link.\nSave videos, photos or the entire carousel.'

class App:
    def __init__(self, root):
        self.root = root
        self.language = 'ru'
        self.installation_language = '' 
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.rows = {}
        self.row_pause_controls = {}
        self.row_cancel_controls = {}
        self.active_row = None
        self.paused_row = None
        self.skip_current = threading.Event()
        self.row_phases = {}
        self._ui_cache = {}
        self.row_cards = {}
        self.row_bars = {}
        self.row_eta = {}
        self.row_details = {}
        self.error_log = []
        self.list_filter = tk.StringVar(value='Все')
        self.detailed_list = False
        self.interface_scale = '100%'
        self.show_completed = True
        self.layout_panels = []
        self.row_files = {}
        self.delete_buttons = {}
        self.next_row_id = 0
        self.pending_jobs = []
        self.jobs_by_key = {}
        self.jobs_by_row = {}
        self.retry_buttons = {}
        self.queue_paused = False
        self.pause_requested = False
        self.active_job = None
        self.active_run = None
        self.active_rows = []
        self.folder_history = []
        self.active_folder = None
        self.access = {'method': 'Без входа', 'email': '', 'password': '', 'file': ''}
        try:
            self.access = json.loads(protect_profile(PROFILE_FILE.read_bytes(), decrypt=True))
        except (OSError, ValueError):
            pass
        root.title(f'ClipFlow {APP_VERSION} — YouTube · GetCourse · Instagram')
        root.geometry('1080x780')
        root.minsize(880, 680)
        root.configure(fg_color=COLORS['background'])
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(2, weight=1)
        self.url = tk.StringVar()
        self.folder = tk.StringVar(value=default_download_folder())
        self.mode = tk.StringVar(value='Видео MP4')
        self.quality = tk.StringVar(value='Лучшее доступное')
        self.instagram_author_folder = tk.BooleanVar(value=True)
        self.instagram_post_folder = tk.BooleanVar(value=True)
        self.instagram_profile_limit = tk.StringVar(value='До 10 публикаций')
        self.save_instagram_description = tk.BooleanVar(value=False)
        self.instagram_description_format = tk.StringVar(value='TXT')
        self.auto_download = tk.BooleanVar(value=True)
        self.playlist = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value='Вставьте ссылку, выберите параметры и нажмите «Скачать».')
        self.access_status = tk.StringVar(value='Без входа')
        self.queue_count = tk.StringVar(value='Пока нет загрузок')
        self.scope_hint = tk.StringVar(value='Одно видео YouTube или первое видео урока GetCourse')
        try:
            settings = json.loads(CONFIG.read_text(encoding='utf-8'))
            self.auto_download.set(settings.get('auto_download', True))
            self.instagram_author_folder.set(settings.get('instagram_author_folder', True))
            self.instagram_post_folder.set(settings.get('instagram_post_folder', True))
            profile_limit = settings.get('instagram_profile_limit', 'До 10 публикаций')
            self.instagram_profile_limit.set(profile_limit if profile_limit in ('Все публикации', 'До 10 публикаций', 'До 50 публикаций', 'До 100 публикаций') else 'До 10 публикаций')
            self.save_instagram_description.set(settings.get('save_instagram_description', False))
            description_format = settings.get('instagram_description_format', 'TXT')
            self.instagram_description_format.set(description_format if description_format in ('TXT', 'MD') else 'TXT')
            self.folder.set(settings.get('folder', self.folder.get()))
            self.detailed_list = settings.get('detailed_list', False)
            self.interface_scale = settings.get('interface_scale', '100%')
            ctk.set_widget_scaling(int(self.interface_scale[:-1]) / 100)
            self.folder_history = settings.get('folders', [self.folder.get()])[:10]
            self.language = settings.get('language', 'ru')
            self.installation_language = settings.get('installation_language', '')
        except (OSError, ValueError):
            pass
        try:
            installed = ((Path(sys.executable).parent if getattr(sys, 'frozen', False) and os.name == 'nt' else BASE) / 'language.txt').read_text(encoding='utf-8').strip()
            if installed != self.installation_language:
                self.installation_language = installed
                self.language = 'en' if installed.endswith(':en') else 'ru'
        except OSError:
            pass
        self.youtube_session = YouTubeSession(AUTH_DIR, protect_profile)
        self.youtube_session.restore_profile()
        self.youtube_connected = bool(self.youtube_session.saved())
        self.youtube_status = tk.StringVar(value='YouTube: сессия сохранена' if self.youtube_connected else 'YouTube: вход не выполнен')
        self.profile_status = tk.StringVar(value=('Сохранён профиль: ' + self.access['email']) if self.access.get('email') else 'Профиль GetCourse не сохранён')
        self.instagram_session = InstagramSession(APP_DATA / 'InstagramAuth', protect_profile)
        self.instagram_session.restore_profile()
        self.instagram_connected = bool(self.instagram_session.saved())
        self.instagram_status = tk.StringVar(value='Instagram: сессия сохранена' if self.instagram_connected else 'Instagram: вход не выполнен')
        self.instagram_scope = tk.StringVar(value='Всё')
        self.getcourse_scope = tk.StringVar(value='Все видео урока')
        self.contexts = {
            'YouTube': {'url': self.url, 'folder': self.folder, 'mode': self.mode, 'quality': self.quality, 'playlist': self.playlist, 'scope_hint': self.scope_hint},
            'GetCourse': {'url': tk.StringVar(), 'folder': tk.StringVar(value=self.folder.get()), 'mode': tk.StringVar(value='Видео MP4'), 'quality': tk.StringVar(value=self.quality.get()), 'playlist': tk.BooleanVar(value=False), 'scope_hint': tk.StringVar(value='Доступ: ' + self.access['method'])},
        }
        self.contexts['Instagram'] = {'url': tk.StringVar(), 'folder': tk.StringVar(value=self.folder.get()), 'mode': tk.StringVar(value='Видео и фото (MP4)'), 'quality': tk.StringVar(value='Лучшее доступное'), 'playlist': tk.BooleanVar(value=False), 'scope_hint': tk.StringVar()}
        icon_path = BASE / 'clipflow.png'
        self._brand_images = {}
        for service, suffix in [('YouTube', ''), ('GetCourse', '-getcourse'), ('Instagram', '-instagram')]:
            image = Image.open(BASE / ('clipflow' + suffix + '.png'))
            self._brand_images[service] = ctk.CTkImage(light_image=image, dark_image=image, size=(34, 34))
        self.brand_image = self._brand_images['YouTube']
        root.after(250, self.update_brand_icon)
        header = ctk.CTkFrame(root, fg_color='transparent')
        header.grid(row=0, column=0, sticky='ew', padx=28, pady=(12, 8))
        header.grid_columnconfigure(2, weight=1)
        self.brand_label = ctk.CTkLabel(header, text='', image=self.brand_image, width=34, height=34)
        self.brand_label.grid(row=0, column=0, rowspan=2, padx=(0, 14))
        self.label(header, 'ClipFlow', size=22, weight='bold').grid(row=0, column=1, sticky='w')
        self.label(header, APP_VERSION, size=12, color=COLORS['muted']).grid(row=0, column=2, sticky='w', padx=12)
        self.build_menu(header)
        
        self.button(header, 'Открыть папку', self.open_folder, kind='tonal', width=145).grid(row=0, column=4, rowspan=2, padx=(12, 0))
        settings_card = ctk.CTkFrame(root, fg_color=COLORS['surface'], corner_radius=12)
        settings_card.grid(row=1, column=0, sticky='ew', padx=28, pady=(0, 12))
        settings_card.grid_columnconfigure(0, weight=1)
        self.tabs = ctk.CTkTabview(settings_card, corner_radius=16, fg_color=COLORS['surface'], segmented_button_fg_color=COLORS['surface_high'], segmented_button_selected_color=COLORS['secondary_container'], segmented_button_selected_hover_color=COLORS['secondary_hover'], segmented_button_unselected_color=COLORS['surface_high'], segmented_button_unselected_hover_color=COLORS['outline_variant'], text_color=COLORS['text'], command=self.activate_tab, anchor='w')
        self.tabs.grid(row=0, column=0, sticky='ew', padx=10, pady=(8, 2))
        for service in ('YouTube', 'Instagram', 'GetCourse'):
            panel = self.tabs.add(service)
            panel.grid_columnconfigure(0, weight=1)
            context = self.contexts[service]
            for name in ('url', 'folder', 'mode', 'quality', 'playlist', 'scope_hint'):
                setattr(self, name, context[name])
            self.label(panel, 'Ссылка на видео или плейлист YouTube' if service == 'YouTube' else 'Ссылка на публикацию или профиль Instagram' if service == 'Instagram' else 'Ссылка на урок или плеер GetCourse', size=12, color=COLORS['secondary']).grid(row=0, column=0, sticky='w', padx=20, pady=(8, 0))
            link_row = ctk.CTkFrame(panel, fg_color='transparent')
            link_row.grid(row=1, column=0, sticky='ew', padx=20, pady=(6, 10))
            link_row.grid_columnconfigure(1, weight=1)
            self.paste_button = self.button(link_row, 'Вставить ссылку', lambda service=service: self.paste_url(replace=True, service=service), width=190)
            self.paste_button.grid(row=0, column=0, padx=(0, 14))
            self.url_entry = self.entry(link_row, self.url, placeholder='https://youtube.com/watch…' if service == 'YouTube' else 'https://www.instagram.com/p/…' if service == 'Instagram' else 'https://…getcourse.ru/…')
            self.url_entry.grid(row=0, column=1, sticky='ew')
            self.url_entry.bind('<Return>', lambda event: self.start(prefer_queue=False))
            self.url_entry.paste_callback = lambda event=None, service=service: self.paste_url(event, service=service)
            controls = ctk.CTkFrame(panel, fg_color='transparent')
            controls.grid(row=2, column=0, sticky='ew', padx=20)
            controls.grid_columnconfigure(3, weight=1)
            self.layout_panels.append(controls)
            controls.bind('<Configure>', lambda event, panel=controls: self.reflow_controls(panel, event.width))
            self.label(controls, 'Формат', size=12, color=COLORS['muted']).grid(row=0, column=0, sticky='w', pady=(0, 6))
            self.mode_box = self.option(controls, self.mode, ['Видео и фото (MP4)', 'Видео MKV', 'Видео WebM', 'Звук MP3'] if service == 'Instagram' else ['Видео MP4', 'Видео MKV', 'Видео WebM', 'Звук MP3'], width=175, command=self.mode_changed)
            self.mode_box.grid(row=1, column=0, sticky='w')
            self.label(controls, 'Качество', size=12, color=COLORS['muted']).grid(row=0, column=1, sticky='w', padx=(24, 0), pady=(0, 6))
            self.quality_box = self.option(controls, self.quality, ['Лучшее доступное'], width=170)
            self.quality_box.grid(row=1, column=1, padx=(24, 0), sticky='w')
            context['start_button'] = self.button(controls, '', lambda: self.start(prefer_queue=False), image=self.command_icon('download'), width=190, height=40, state='disabled')
            context['start_button'].grid(row=1, column=4, sticky='e', padx=(16, 0))
            context['start_button'].bind('<Enter>', lambda event: self.show_download_tooltip())
            context['start_button'].bind('<Leave>', lambda event: self.hide_tooltip())
            auto_switch = ctk.CTkSwitch(controls, text='Автоскачивание', variable=self.auto_download, command=self.save_settings, width=190, switch_width=36, switch_height=20, font=(FONT_FAMILY, 12), text_color=COLORS['text'], progress_color=COLORS['primary_action'], fg_color=COLORS['outline_variant'], button_color=COLORS['secondary'], button_hover_color=COLORS['text'])
            auto_switch.grid(row=0, column=4, sticky='e', padx=(16, 0), pady=(0, 6))
            context['quality_status'] = tk.StringVar()
            self.label(controls, '', textvariable=context['quality_status'], size=11, height=16, color=COLORS['muted']).grid(row=2, column=1, sticky='w', padx=(24, 0), pady=(3, 0))
            if service == 'YouTube':
                self.label(controls, 'Плейлист', size=12, color=COLORS['muted']).grid(row=0, column=2, sticky='w', padx=(24, 0), pady=(0, 6))
                self.playlist_switch = ctk.CTkSwitch(controls, text='Плейлист YouTube целиком', variable=self.playlist, command=self.scope_changed, progress_color=COLORS['primary_action'], fg_color=COLORS['outline_variant'], button_color=COLORS['secondary'], button_hover_color=COLORS['text'], text_color=COLORS['text'], font=(FONT_FAMILY, 13), switch_width=42, switch_height=24)
                self.playlist_switch.grid(row=1, column=2, padx=(24, 0), sticky='w')
            elif service == 'Instagram':
                self.label(controls, 'Содержимое', size=12, color=COLORS['muted']).grid(row=0, column=2, sticky='w', padx=(24, 0), pady=(0, 6))
                self.instagram_scope_box = self.option(controls, self.instagram_scope, ['Всё', 'Только видео', 'Только фото'], width=180, command=self.instagram_scope_changed)
                self.instagram_scope_box.grid(row=1, column=2, sticky='w', padx=(24, 0))
                description_row = ctk.CTkFrame(panel, fg_color='transparent')
                description_row.grid(row=4, column=0, sticky='w', padx=20, pady=(0, 8))
                self.instagram_description_switch = ctk.CTkSwitch(description_row, text='Сохранять описание', variable=self.save_instagram_description, command=self.save_settings, progress_color=COLORS['primary_action'], fg_color=COLORS['outline_variant'], button_color=COLORS['secondary'], button_hover_color=COLORS['text'], text_color=COLORS['text'], font=(FONT_FAMILY, 13), switch_width=42, switch_height=24)
                self.instagram_description_switch.grid(row=0, column=0, sticky='w')
                self.instagram_description_format_box = self.option(description_row, self.instagram_description_format, ['TXT', 'MD'], width=90, command=lambda value: self.save_settings())
                self.instagram_description_format_box.grid(row=0, column=1, padx=(16, 0))
                self.instagram_author_folder_switch = ctk.CTkSwitch(description_row, text='Папка с ником автора', variable=self.instagram_author_folder, command=self.save_settings, progress_color=COLORS['primary_action'], fg_color=COLORS['outline_variant'], button_color=COLORS['secondary'], button_hover_color=COLORS['text'], text_color=COLORS['text'], font=(FONT_FAMILY, 13), switch_width=42, switch_height=24)
                self.instagram_author_folder_switch.grid(row=0, column=2, padx=(24, 0), sticky='w')
                self.instagram_post_folder_switch = ctk.CTkSwitch(description_row, text='Папка для каждого поста', variable=self.instagram_post_folder, command=self.save_settings, progress_color=COLORS['primary_action'], fg_color=COLORS['outline_variant'], button_color=COLORS['secondary'], button_hover_color=COLORS['text'], text_color=COLORS['text'], font=(FONT_FAMILY, 13), switch_width=42, switch_height=24)
                self.instagram_post_folder_switch.grid(row=1, column=0, columnspan=2, sticky='w', pady=(8, 0))
                self.instagram_profile_limit_box = self.option(description_row, self.instagram_profile_limit, ['До 10 публикаций', 'До 50 публикаций', 'До 100 публикаций', 'Все публикации'], width=190, command=lambda _: self.save_settings())
                self.instagram_profile_limit_box.grid(row=1, column=2, sticky='w', padx=(24, 0), pady=(8, 0))
                self.playlist_switch = None
            else:
                self.label(controls, 'Видео урока', size=12, color=COLORS['muted']).grid(row=0, column=2, sticky='w', padx=(24, 0), pady=(0, 6))
                self.access_button = self.button(controls, 'Настроить доступ', self.configure_access, kind='outline', width=185)
                # Account action is next to profile status.
                self.playlist_switch = None
            folder_row = ctk.CTkFrame(panel, fg_color='transparent')
            folder_row.grid(row=3, column=0, sticky='ew', padx=20, pady=(12, 8))
            folder_row.grid_columnconfigure(1, weight=1)
            self.label(folder_row, 'Папка', size=13, color=COLORS['muted']).grid(row=0, column=0, padx=(0, 14))
            self.folder_entry = self.entry(folder_row, self.folder)
            self.folder_entry.grid(row=0, column=1, sticky='ew')
            self.browse = self.button(folder_row, 'Выбрать…', self.choose_folder, kind='tonal', width=110)
            self.browse.grid(row=0, column=2, padx=(12, 0))
            history = self.option(folder_row, tk.StringVar(value='Недавние'), self.folder_history or [self.folder.get()], width=120)
            history._i18n_user_values = True
            history.configure(command=lambda value, variable=self.folder: (variable.set(value), self.remember_folder(value)))
            history.grid(row=0, column=3, padx=(8, 0))
            context['history'] = history
            if service == 'GetCourse':
                profile_row = ctk.CTkFrame(panel, fg_color='transparent')
                profile_row.grid(row=5, column=0, sticky='ew', padx=20, pady=(0, 8))
                profile_row.grid_columnconfigure(0, weight=1)
                self.label(profile_row, '', textvariable=self.profile_status, size=12, color=COLORS['secondary'], wraplength=700).grid(row=0, column=0, sticky='w')
                self.access_button = self.button(profile_row, 'Настроить доступ', self.configure_access, kind='outline', width=150)
                self.access_button.grid(row=0, column=1, padx=(0, 8))
                self.button(profile_row, 'Выйти', self.logout_profile, kind='outline', width=80).grid(row=0, column=2)


            if service == 'GetCourse':
                self.getcourse_scope_box = self.option(controls, self.getcourse_scope, ['Первое видео', 'Все видео урока', 'Выбрать видео'], width=195)
                self.getcourse_scope_box.grid(row=1, column=2, sticky='w', padx=(24, 0))
                self.getcourse_scope_box.configure(command=self.getcourse_scope_changed)
            if service == 'YouTube':
                auth_row = ctk.CTkFrame(panel, fg_color='transparent')
                auth_row.grid(row=5, column=0, sticky='ew', padx=20, pady=(0, 8))
                auth_row.grid_columnconfigure(0, weight=1)
                self.label(auth_row, '', textvariable=self.youtube_status, size=12, color=COLORS['secondary']).grid(row=0, column=0, sticky='w')
                self.youtube_login_button = self.button(auth_row, 'Войти в YouTube', self.signin_youtube, kind='outline', width=155)
                self.youtube_login_button.grid(row=0, column=1, padx=(8, 8))
                self.button(auth_row, 'Выйти', self.logout_youtube, kind='outline', width=80).grid(row=0, column=2)
            if service == 'Instagram':
                auth_row = ctk.CTkFrame(panel, fg_color='transparent')
                auth_row.grid(row=5, column=0, sticky='ew', padx=20, pady=(0, 8))
                auth_row.grid_columnconfigure(0, weight=1)
                self.label(auth_row, '', textvariable=self.instagram_status, size=12, color=COLORS['secondary']).grid(row=0, column=0, sticky='w')
                self.instagram_login_button = self.button(auth_row, 'Войти в Instagram', self.signin_instagram, kind='outline', width=165)
                self.instagram_login_button.grid(row=0, column=1, padx=8)
                self.instagram_logout_button = self.button(auth_row, 'Выйти', self.logout_instagram, kind='outline', width=80)
                self.instagram_logout_button.grid(row=0, column=2)
                self.instagram_auth_row = auth_row
                auth_row.grid_remove()
            for name in ('url_entry', 'paste_button', 'mode_box', 'quality_box', 'folder_entry', 'browse', 'playlist_switch'):
                context[name] = getattr(self, name)
            context['url'].trace_add('write', lambda *args, service=service: self.schedule_quality_check(service))
        self.tabs.set('YouTube')
        self.activate_tab()
        self.queue_card = ctk.CTkFrame(root, fg_color=COLORS['surface'], corner_radius=12)
        self.queue_card.grid(row=2, column=0, sticky='nsew', padx=28, pady=(0, 18))
        self.queue_card.grid_columnconfigure(0, weight=1)
        self.queue_card.grid_rowconfigure(1, weight=1)
        queue_header = ctk.CTkFrame(self.queue_card, fg_color='transparent')
        queue_header.grid(row=0, column=0, sticky='ew', padx=20, pady=(10, 8))
        queue_header.grid_columnconfigure(1, weight=1)
        self.label(queue_header, 'Загрузки', size=19, weight='bold').grid(row=0, column=0, sticky='w')
        self.label(queue_header, '', size=12, color=COLORS['secondary'], textvariable=self.queue_count).grid(row=1, column=0, sticky='w', pady=(3, 0))
        self.cancel_button = self.button(queue_header, 'Отменить', self.request_cancel, kind='outline', width=110, state='disabled')
        # Active download controls are displayed on its own row.
        # Kept for compatibility; manual links use Enter or Add.
        self.add_button = self.button(queue_header, '+ В очередь', lambda: self.start(auto_start=False), kind='tonal', width=125)
        # Queue insertion is automatic.
        self.pause_button = self.button(queue_header, 'Пауза', self.toggle_pause, kind='outline', width=95, state='disabled')

        list_actions = self.option(queue_header, tk.StringVar(value='Действия'), ['Очистить список', 'Удалить все файлы'], width=150)
        list_actions.configure(command=lambda action: self.clear_download_list() if action == 'Очистить список' else self.confirm_delete_files(list(self.row_files)))
        list_actions.configure(height=26)
        self.filter_box = ctk.CTkSegmentedButton(queue_header, values=['Все', 'Активные', 'Завершённые', 'Ошибки'], variable=self.list_filter, command=lambda _: self.refresh_list(), height=30, fg_color=COLORS['surface_high'], selected_color=COLORS['secondary_container'], unselected_color=COLORS['surface_high'], text_color=COLORS['text'])
        self.filter_box.grid(row=0, column=1, sticky='e', padx=12)
        self.empty_panel = ctk.CTkFrame(self.queue_card, fg_color='transparent')
        self.empty_panel.grid(row=1, column=0, sticky='nsew', padx=20, pady=(0, 20))
        self.empty_panel.grid_columnconfigure(0, weight=1)
        self.empty_panel.grid_rowconfigure(0, weight=1)
        empty_content = ctk.CTkFrame(self.empty_panel, fg_color='transparent')
        empty_content.grid(row=0, column=0)
        self.empty_icon = ctk.CTkLabel(empty_content, text='', image=self.brand_image, width=34, height=34, corner_radius=17, fg_color=COLORS['primary_container'], text_color=COLORS['on_primary_container'], font=(FONT_FAMILY, 26))
        self.empty_icon.pack(pady=(0, 8))
        self.empty_title = self.label(empty_content, 'Ваши видео. В вашей папке.', size=20, weight='bold')
        self.empty_title.pack()
        self.empty_description = self.label(empty_content, 'Вставьте ссылку на видео или плейлист.\nКачество, формат и папка — на панели выше.', size=13, color=COLORS['muted'], justify='center')
        self.empty_description.pack(pady=(6, 0))
        self.empty_panel.bind('<Configure>', self.resize_empty)
        self.queue_panel = ctk.CTkScrollableFrame(self.queue_card, fg_color='transparent', scrollbar_button_color=COLORS['outline_variant'], scrollbar_button_hover_color=COLORS['outline'])
        self.queue_panel.grid_columnconfigure(0, weight=1)
        footer = ctk.CTkFrame(root, fg_color='transparent')
        footer.grid(row=3, column=0, sticky='ew', padx=30, pady=(0, 12))
        footer.grid_columnconfigure(0, weight=1)
        self.status_label = self.label(footer, '', textvariable=self.status, size=12, color=COLORS['muted'], wraplength=970)
        self.status_label.grid(row=0, column=0, sticky='w', pady=(0, 9))
        self.progress = ctk.CTkProgressBar(footer, height=5, corner_radius=3, fg_color=COLORS['outline_variant'], progress_color=COLORS['tertiary'])
        self.progress.grid(row=1, column=0, sticky='ew')
        self.progress.set(0)
        self.url_entry.focus_set()
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.refresh_auth_controls()
        self.localize_ui()
        self._poll_after = root.after(120, self.poll)

    def activate_tab(self):
        service = self.tabs.get()
        for name, value in self.contexts[service].items():
            setattr(self, name, value)
        with self.redraw_transaction():
            self.apply_palette(service)
            if hasattr(self, 'empty_description'):
                self.empty_description.configure(text='Вставьте ссылку на Reel или публикацию.\nСохраняйте видео, фото или всю карусель.' if service == 'Instagram' else 'Вставьте ссылку на видео или плейлист.\nКачество, формат и папка — на панели выше.')
            self.refresh_download_buttons()

    @contextmanager
    def redraw_transaction(self):
        """Hold painting of this app's windows until the whole theme is ready."""
        if IS_MAC:
            with atomic_redraw(self.root):
                yield
            return
        if os.name != 'nt' or not self.root.winfo_ismapped():
            yield
            return
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.GetParent.argtypes = [wintypes.HWND]
        user32.GetParent.restype = wintypes.HWND
        user32.RedrawWindow.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.HANDLE, wintypes.UINT]
        handles = []
        def collect(widget):
            if widget.winfo_ismapped():
                handles.append(widget.winfo_id())
            for child in widget.winfo_children():
                collect(child)
        collect(self.root)
        window = user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
        handles.append(window)
        for handle in handles:
            user32.SendMessageW(handle, 0x000B, 0, 0)  # WM_SETREDRAW
        try:
            yield
            self.root.update_idletasks()
        finally:
            for handle in reversed(handles):
                user32.SendMessageW(handle, 0x000B, 1, 0)
            user32.RedrawWindow(window, None, None, 0x0185)  # invalidate, erase, all children, update now

    def update_brand_icon(self):
        service = self.tabs.get()
        self.brand_image = self._brand_images[service]
        self.update_widget(self.brand_label, image=self.brand_image)
        if hasattr(self, 'empty_icon'):
            self.update_widget(self.empty_icon, image=self.brand_image)

    def apply_palette(self, service):
        palette = {'GetCourse': GETCOURSE_COLORS, 'Instagram': INSTAGRAM_COLORS}.get(service, YOUTUBE_COLORS)
        old = COLORS.copy()
        COLORS.update(palette)
        mapping = {value.lower(): palette[key] for key, value in old.items()}
        # Public CTk color options cover controls, nested tab buttons and scrollbars.
        options = ('fg_color', 'bg_color', 'text_color', 'hover_color', 'border_color',
                   'progress_color', 'button_color', 'button_hover_color', 'placeholder_text_color',
                   'selected_color', 'selected_hover_color', 'unselected_color', 'unselected_hover_color',
                   'segmented_button_fg_color', 'segmented_button_selected_color',
                   'segmented_button_selected_hover_color', 'segmented_button_unselected_color',
                   'segmented_button_unselected_hover_color', 'dropdown_fg_color',
                   'dropdown_hover_color', 'dropdown_text_color', 'scrollbar_button_color',
                   'scrollbar_button_hover_color')
        def visit(widget):
            if getattr(widget, '_fixed_source_theme', False):
                return
            if not isinstance(widget, (ctk.CTkBaseClass, ctk.CTk, ctk.CTkToplevel)):
                for child in widget.winfo_children():
                    visit(child)
                return
            changes = {}
            roles = getattr(widget, '_palette_roles', {})
            for option in options:
                try:
                    value = widget.cget(option)
                    if option in roles:
                        if value != palette[roles[option]]:
                            changes[option] = palette[roles[option]]
                    elif isinstance(value, str) and value.lower() in mapping:
                        role = next(key for key, color in old.items() if color.lower() == value.lower())
                        roles[option] = role
                        if value != palette[role]:
                            changes[option] = palette[role]
                except (ValueError, AttributeError, tk.TclError):
                    pass
            widget._palette_roles = roles
            try:
                if changes:
                    widget.configure(**changes)
            except (ValueError, AttributeError, tk.TclError):
                for option, value in changes.items():
                    try:
                        widget.configure(**{option: value})
                    except (ValueError, AttributeError, tk.TclError):
                        pass
            for child in widget.winfo_children():
                visit(child)
        visit(self.root)
        self.update_brand_icon()

    def resize_empty(self, event):
        # Hide decoration first, preserving both explanatory lines at small heights.
        if event.height >= 85 and not self.empty_title.winfo_manager():
            self.empty_title.pack(before=self.empty_description)
        compact = event.height < 160
        if compact:
            self.empty_icon.pack_forget()
        elif not self.empty_icon.winfo_manager():
            self.empty_icon.pack(before=self.empty_title if self.empty_title.winfo_manager() else self.empty_description, pady=(0, 8))
        self.empty_title.configure(font=(FONT_FAMILY, 17 if compact else 20, 'bold'))
        if event.height < 85:
            self.empty_title.pack_forget()
        elif not self.empty_title.winfo_manager():
            self.empty_title.pack(before=self.empty_description)
        self.empty_description.configure(wraplength=max(400, event.width - 40))

    def label(self, parent, text, size=13, color=None, weight='normal', **kwargs):
        return ctk.CTkLabel(parent, text=text, text_color=color or COLORS['text'], font=(FONT_FAMILY, size, weight), **kwargs)

    def command_icon(self, name):
        from PIL import ImageDraw
        if not hasattr(self, '_command_icons'):
            self._command_icons = {}
        if name not in self._command_icons:
            image = Image.new('RGBA', (64, 64))
            draw = ImageDraw.Draw(image)
            color = '#F2F2F5'
            if name == 'play':
                draw.polygon([(20, 12), (20, 52), (51, 32)], fill=color)
            elif name == 'pause':
                draw.rounded_rectangle((18, 12, 26, 52), radius=2, fill=color)
                draw.rounded_rectangle((38, 12, 46, 52), radius=2, fill=color)
            elif name == 'cancel':
                draw.line((16, 16, 48, 48), fill=color, width=5)
                draw.line((48, 16, 16, 48), fill=color, width=5)
            elif name == 'more':
                for x in (14, 32, 50):
                    draw.ellipse((x-3, 29, x+3, 35), fill=color)
            elif name == 'folder':
                draw.line([(8, 48), (8, 15), (26, 15), (32, 23), (56, 23), (56, 48), (8, 48)], fill=color, width=4)
            elif name == 'download':
                draw.line([(32, 8), (32, 40)], fill=color, width=5)
                draw.line([(20, 29), (32, 41), (44, 29)], fill=color, width=5)
                draw.line([(12, 42), (12, 54), (52, 54), (52, 42)], fill=color, width=5)
            else:
                draw.rounded_rectangle((14, 14, 50, 54), radius=4, outline=color, width=4)
                draw.rounded_rectangle((23, 8, 41, 21), radius=3, fill=color)
                draw.line((23, 35, 41, 35), fill=color, width=4)
                draw.line((32, 26, 32, 44), fill=color, width=4)
            self._command_icons[name] = ctk.CTkImage(light_image=image, dark_image=image, size=(24, 24) if name == 'download' else (16, 16))
        return self._command_icons[name]

    def button(self, parent, text, command, kind='primary', **kwargs):
        style = dict(fg_color=COLORS['primary_action'], hover_color=COLORS['primary_hover'], text_color=COLORS['on_primary'])
        if kind == 'tonal':
            style = dict(fg_color=COLORS['secondary_container'], hover_color=COLORS['secondary_hover'], text_color=COLORS['text'])
        elif kind == 'outline':
            style = dict(fg_color='transparent', hover_color=COLORS['surface_high'], text_color=COLORS['secondary'], border_width=1, border_color=COLORS['outline_variant'])
        icon_name = {'Вставить ссылку': 'paste', 'Открыть папку': 'folder', 'Пауза': 'pause', 'Отменить': 'cancel', '…': 'more'}.get(text)
        if icon_name:
            kwargs['image'] = self.command_icon(icon_name)
            if text == '…':
                text = ''
        return ctk.CTkButton(parent, text=text, command=command, height=kwargs.pop('height', 36), corner_radius=10, font=(FONT_FAMILY, 13, 'bold'), **style, **kwargs)

    def entry(self, parent, variable, placeholder=None, **kwargs):
        return MaterialEntry(parent, textvariable=variable, placeholder_text=placeholder, height=38, corner_radius=10, border_width=1, fg_color=COLORS['surface_high'], border_color=COLORS['outline_variant'], text_color=COLORS['text'], placeholder_text_color=COLORS['outline'], font=(FONT_FAMILY, 13), **kwargs)

    def option(self, parent, variable, values, **kwargs):
        return ctk.CTkOptionMenu(parent, variable=variable, values=values, height=36, corner_radius=10, fg_color=COLORS['surface_high'], button_color=COLORS['secondary_container'], button_hover_color=COLORS['secondary_hover'], text_color=COLORS['text'], dropdown_fg_color=COLORS['surface_high'], dropdown_hover_color=COLORS['secondary_container'], dropdown_text_color=COLORS['text'], font=(FONT_FAMILY, 13), dropdown_font=(FONT_FAMILY, 13), **kwargs)

    def notice(self, title, message):
        dialog = ctk.CTkToplevel(self.root)
        dialog.title(self.translate(title))
        dialog.geometry('520x280')
        dialog.configure(fg_color=COLORS['surface'])
        dialog.transient(self.root)
        dialog.grab_set()
        self.label(dialog, title, size=21, weight='bold').pack(anchor='w', padx=24, pady=(24, 12))
        box = ctk.CTkTextbox(dialog, fg_color='transparent', text_color=COLORS['muted'], font=(FONT_FAMILY, 13), wrap='word')
        box.pack(fill='both', expand=True, padx=20)
        box.insert('1.0', message)
        box.configure(state='disabled')
        self.button(dialog, 'Понятно', dialog.destroy, width=120).pack(anchor='e', padx=24, pady=18)

    def configure_access(self):
        dialog = ctk.CTkToplevel(self.root)
        dialog.title('Доступ GetCourse')
        dialog.geometry('580x660')
        dialog.configure(fg_color=COLORS['background'])
        dialog.transient(self.root)
        dialog.grab_set()
        panel = ctk.CTkFrame(dialog, fg_color=COLORS['surface'], corner_radius=12)
        panel.pack(fill='both', expand=True, padx=20, pady=20)
        panel.grid_columnconfigure(0, weight=1)
        self.label(panel, 'Доступ к закрытым урокам', size=21, weight='bold').grid(row=0, column=0, columnspan=2, sticky='w', padx=20, pady=(20, 12))
        method = tk.StringVar(value=self.access['method'])
        selector = self.option(panel, method, ['Без входа', *BROWSERS, 'Email и пароль', 'Файл cookies'])
        selector.grid(row=1, column=0, columnspan=2, sticky='ew', padx=20, pady=(0, 12))
        help_text = tk.StringVar()
        self.label(panel, '', textvariable=help_text, size=12, color=COLORS['muted'], wraplength=490, justify='left', height=80, anchor='w').grid(row=2, column=0, columnspan=2, sticky='ew', padx=20, pady=(0, 16))
        email = tk.StringVar(value=self.access['email'])
        password = tk.StringVar(value=self.access['password'])
        cookie_file = tk.StringVar(value=self.access['file'])
        self.label(panel, 'Email GetCourse', color=COLORS['secondary']).grid(row=3, column=0, sticky='w', padx=20)
        email_entry = self.entry(panel, email)
        email_entry.grid(row=4, column=0, columnspan=2, sticky='ew', padx=20, pady=(5, 12))
        self.label(panel, 'Пароль GetCourse', color=COLORS['secondary']).grid(row=5, column=0, sticky='w', padx=20)
        password_entry = self.entry(panel, password, show='•')
        password_entry.grid(row=6, column=0, columnspan=2, sticky='ew', padx=20, pady=(5, 12))
        self.label(panel, 'Файл cookies · формат Netscape', color=COLORS['secondary']).grid(row=7, column=0, sticky='w', padx=20)
        file_entry = self.entry(panel, cookie_file)
        file_entry.grid(row=8, column=0, sticky='ew', padx=(20, 10), pady=(5, 12))
        def browse():
            path = filedialog.askopenfilename(parent=dialog, title=self.translate('Файл cookies'), filetypes=[('Cookies', '*.txt'), (ui_text('Все файлы'), '*.*')])
            if path:
                cookie_file.set(path)
        file_button = self.button(panel, 'Выбрать', browse, kind='tonal', width=110)
        file_button.grid(row=8, column=1, padx=(0, 20))
        def update_fields(*_):
            selected = method.get()
            if selected in BROWSERS:
                help_text.set(f'Откройте урок в {selected} и войдите в аккаунт школы.\nЗатем полностью закройте браузер, нажмите «Применить» и скачайте урок.\nПрограмма прочитает сохранённый вход из профиля браузера.\nЕсли чтение не удаётся, выберите email и пароль или файл cookies.')
            elif selected == 'Email и пароль':
                help_text.set(platform_text('Введите email и пароль от аккаунта вашей школы GetCourse.\nПрограмма войдёт в школу из ссылки на урок.\nВставка: ⌘+V, Shift+Insert или правая кнопка мыши.\nДанные сохраняются с защитой macOS Keychain.'))
            elif selected == 'Файл cookies':
                help_text.set('Выберите экспорт cookies в формате Netscape из браузера,\nв котором вы вошли в школу и открыли урок.\nПрограмма использует сохранённый вход из этого файла.\nИсходный файл не изменяется.')
            else:
                help_text.set('Подходит для открытых уроков и прямых ссылок на плеер.\nДля закрытого урока выберите браузер, email и пароль\nили файл cookies.\nВход должен давать доступ к этому уроку.')
            state = 'normal' if method.get() == 'Email и пароль' else 'disabled'
            email_entry.configure(state=state)
            password_entry.configure(state=state)
            state = 'normal' if method.get() == 'Файл cookies' else 'disabled'
            file_entry.configure(state=state)
            file_button.configure(state=state)
        selector.configure(command=update_fields)
        update_fields()
        self.label(panel, platform_text('Профиль сохраняется с защитой macOS Keychain для этого пользователя.\nКнопка «Выйти» удаляет сохранённые данные из программы.'), size=12, color=COLORS['muted'], justify='left').grid(row=9, column=0, columnspan=2, sticky='w', padx=20, pady=(8, 18))
        def save():
            if method.get() == 'Email и пароль' and not (email.get().strip() and password.get()):
                self.status.set('Введите email и пароль GetCourse.')
                return
            if method.get() == 'Файл cookies' and not Path(cookie_file.get()).is_file():
                self.status.set('Выберите существующий файл cookies.')
                return
            self.access = {'method': method.get(), 'email': email.get().strip() if method.get() == 'Email и пароль' else '', 'password': password.get() if method.get() == 'Email и пароль' else '', 'file': cookie_file.get() if method.get() == 'Файл cookies' else ''}
            try:
                PROFILE_FILE.parent.mkdir(parents=True, exist_ok=True)
                PROFILE_FILE.write_bytes(protect_profile(json.dumps(self.access).encode('utf-8')))
            except OSError as error:
                self.notice('Профиль не сохранён', str(error))
                return
            self.profile_status.set('Сохранён профиль: ' + (self.access['email'] or method.get()))
            self.access_status.set(method.get())
            self.getcourse_scope_changed()
            self.access_button.configure(text='Доступ: ' + ('email' if method.get() == 'Email и пароль' else method.get()))
            dialog.destroy()
        self.button(panel, 'Применить', save, width=145).grid(row=10, column=0, sticky='w', padx=20, pady=(0, 20))
        self.button(panel, 'Отмена', dialog.destroy, kind='outline', width=110).grid(row=10, column=1, sticky='e', padx=20, pady=(0, 20))

    def mode_changed(self, *_):
        self.quality_box.configure(state='disabled' if self.mode.get() == 'Звук MP3' else 'normal')

    def scope_changed(self):
        self.scope_hint.set('Все доступные видео плейлиста · отдельная папка · номера по порядку' if self.playlist.get() else 'Одно видео YouTube')

    def getcourse_scope_changed(self, *_):
        self.contexts['GetCourse']['scope_hint'].set('Доступ: ' + self.access['method'])

    def select_lesson_videos(self, entries, gate, result):
        dialog = ctk.CTkToplevel(self.root)
        dialog.title('Выбор видео урока')
        dialog.geometry('640x480')
        dialog.configure(fg_color=COLORS['background'])
        dialog.transient(self.root)
        dialog.grab_set()
        self.label(dialog, 'Какие видео скачать?', size=21, weight='bold').pack(anchor='w', padx=20, pady=18)
        panel = ctk.CTkScrollableFrame(dialog, fg_color=COLORS['surface'])
        panel.pack(fill='both', expand=True, padx=20)
        selected = []
        for index, entry in enumerate(entries):
            variable = tk.BooleanVar(value=True)
            selected.append(variable)
            ctk.CTkCheckBox(panel, text=f'{index+1:03d} · {entry.get("title") or "Видео"}', variable=variable, fg_color=COLORS['primary_action'], text_color=COLORS['text'], font=(FONT_FAMILY, 12)).pack(anchor='w', padx=8, pady=10)
        def finish(cancel=False):
            indexes = [] if cancel else [index for index, var in enumerate(selected) if var.get()]
            if not indexes and not cancel:
                return
            result.extend(indexes)
            if cancel:
                self.cancel.set()
            dialog.destroy()
            gate.set()
        actions = ctk.CTkFrame(dialog, fg_color='transparent')
        actions.pack(fill='x', padx=20, pady=18)
        self.button(actions, 'Скачать выбранные', finish, width=185).pack(side='right')
        self.button(actions, 'Отмена', lambda: finish(True), kind='outline', width=110).pack(side='left')
        dialog.protocol('WM_DELETE_WINDOW', lambda: finish(True))

    def select_url(self):
        self.url_entry.focus_set()
        self.url_entry.select_range(0, 'end')
        self.url_entry.icursor('end')

    def url_shortcut(self, event):
        key = edit_key(event)
        if key == 'v':
            return self.paste_url(event)
        if key == 'a':
            self.select_url()
            return 'break'
        if key in ('c', 'x'):
            self.url_entry.event_generate('<<Copy>>' if key == 'c' else '<<Cut>>')
            return 'break'

    def paste_url(self, event=None, replace=False, service=None):
        service = service or self.tabs.get()
        entry = self.contexts[service]['url_entry']
        try:
            text = clipboard_text(self.root).strip()
        except tk.TclError:
            self.status.set('В буфере обмена нет текста. Скопируйте ссылку.')
            return 'break'
        if not text:
            self.status.set('Буфер обмена пуст. Сначала скопируйте ссылку.')
            return 'break'
        # Focus before editing also commits native focus/selection state on macOS.
        entry.focus_set()
        if replace:
            entry.delete(0, 'end')
        elif entry.select_present():
            entry.delete('sel.first', 'sel.last')
        entry.insert('insert', text)
        self.status.set('Ссылка вставлена. Выберите параметры и нажмите «Скачать».')
        return 'break'

    def schedule_quality_check(self, service):
        context = self.contexts[service]
        context['quality_pending'] = True
        self.refresh_download_buttons()
        context['quality_request'] = context.get('quality_request', 0) + 1
        request = context['quality_request']
        if context.get('quality_after'):
            self.root.after_cancel(context['quality_after'])
        context['quality'].set('Лучшее доступное')
        context['quality_box'].configure(values=['Лучшее доступное'])
        context['quality_box']._i18n_values = ['Лучшее доступное']
        context['quality_after'] = self.root.after(650, lambda: self.check_quality(service, request))

    def check_quality(self, service, request):
        context = self.contexts[service]
        context['quality_after'] = None
        url = context['url'].get().strip()
        if not url.startswith(('https://', 'http://')):
            context['quality_pending'] = False
            self.refresh_download_buttons()
            context['quality_status'].set('')
            return
        if service == 'Instagram' and profile_username(url):
            # A profile has no single quality list; avoid traversing it during a URL probe.
            self.events.put(('quality_result', (service, request, [], None)))
            return
        context['quality_status'].set('Проверяю качество…')
        access = dict(self.access) if service == 'GetCourse' else {'method': service + ' session'} if getattr(self, service.lower() + '_connected', False) else None
        def inspect():
            try:
                options = download_options(str(BASE), 'Видео — MP4', 'Лучшее доступное', lambda data: None, access)
                options.update(skip_download=True, socket_timeout=15, retries=1, extractor_retries=1, format=None)
                options.pop('postprocessors', None)
                cookies = options.pop('_cookies_source', None)
                yt_auth = options.pop('_youtube_session', False)
                ig_auth = options.pop('_instagram_session', False)
                with yt_dlp.YoutubeDL(options) as ydl:
                    ydl.add_info_extractor(GetCourseRuPlayerIE())
                    ydl.add_info_extractor(ClipFlowInstagramIE())
                    if yt_auth:self.youtube_session.apply(ydl.cookiejar)
                    if ig_auth:self.instagram_session.apply(ydl.cookiejar)
                    if cookies:ydl.cookiejar.load(cookies, ignore_discard=True, ignore_expires=True)
                    info = ydl.extract_info(url, download=False)
                    heights = set()
                    def collect(item):
                        if not item:return
                        for fmt in item.get('formats') or []:
                            height = fmt.get('height')
                            if height and fmt.get('vcodec') != 'none':heights.add(int(height))
                        for entry in item.get('entries') or []:collect(entry)
                    collect(info)
                self.events.put(('quality_result', (service, request, sorted(heights, reverse=True), None)))
            except Exception:
                self.events.put(('quality_result', (service, request, [], 'Не удалось проверить качество')))
        threading.Thread(target=inspect, daemon=True).start()

    def show_url_menu(self, event):
        return self.url_entry.edit_menu(event)

    def save_settings(self):
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        CONFIG.write_text(json.dumps({'folder': self.folder.get(), 'quality': self.quality.get(), 'auto_download': self.auto_download.get(), 'instagram_author_folder': self.instagram_author_folder.get(), 'instagram_post_folder': self.instagram_post_folder.get(), 'instagram_profile_limit': self.instagram_profile_limit.get(), 'save_instagram_description': self.save_instagram_description.get(), 'instagram_description_format': self.instagram_description_format.get(), 'folders': self.folder_history, 'language': self.language, 'installation_language': self.installation_language, 'detailed_list': self.detailed_list, 'interface_scale': self.interface_scale}, ensure_ascii=False), encoding='utf-8')

    def remember_folder(self, folder):
        self.folder_history = [folder] + [item for item in self.folder_history if os.path.normcase(item) != os.path.normcase(folder)]
        self.folder_history = self.folder_history[:10]
        for context in self.contexts.values():
            if 'history' in context:
                context['history'].configure(values=self.folder_history)
                context['history'].set('Недавние')
        try:
            self.save_settings()
        except OSError:
            pass

    def logout_profile(self):
        try:
            PROFILE_FILE.unlink(missing_ok=True)
        except OSError as error:
            self.notice('Не удалось выйти', str(error))
            return
        self.access = {'method': 'Без входа', 'email': '', 'password': '', 'file': ''}
        for job in self.pending_jobs:
            if job['service'] == 'GetCourse':
                job['access'] = None
        self.profile_status.set('Профиль GetCourse не сохранён')
        self.access_button.configure(text='Настроить доступ')
        self.contexts['GetCourse']['scope_hint'].set('Для закрытого урока настройте доступ.')

    def choose_folder(self):
        chosen = filedialog.askdirectory(initialdir=self.folder.get(), title=self.translate('Папка для скачивания'))
        if chosen:
            self.folder.set(chosen)
            self.remember_folder(chosen)

    def open_folder(self):
        path = Path(self.active_folder or self.folder.get())
        if path.is_dir():
            reveal_folder(path)
        else:
            self.notice('Папка', 'Сначала выберите существующую папку.')

    def set_busy(self, busy):
        self.busy = busy
        self.refresh_download_buttons()
        self.cancel_button.configure(state='normal' if busy else 'disabled')
        self.pause_button.configure(state='normal' if busy or self.queue_paused else 'disabled')

    def start(self, auto_start=True, prefer_queue=True):
        if self.contexts[self.tabs.get()].get('quality_pending'):
            self.status.set('Проверяю качество…')
            return
        if prefer_queue and auto_start and not self.busy and self.pending_jobs:
            self.launch_next()
            return
        url = self.url.get().strip()
        if not supported_url(url):
            self.notice('Проверьте ссылку', 'Вставьте ссылку YouTube, GetCourse или публикации Instagram.')
            return
        host = (urlparse(url).hostname or '').lower()
        is_youtube = host == 'youtu.be' or host == 'youtube.com' or host.endswith('.youtube.com')
        is_instagram = is_instagram_url(url) or bool(profile_username(url))
        detected_service = 'Instagram' if is_instagram else 'YouTube' if is_youtube else 'GetCourse'
        if self.tabs.get() != detected_service:
            self.notice('Выберите вкладку', 'Выберите вкладку платформы из ссылки: YouTube, GetCourse или Instagram.')
            return
        whole_playlist = self.playlist.get()
        if whole_playlist and not youtube_playlist_url(url):
            self.notice('Плейлист YouTube', 'Нужна ссылка с параметром list=…\nДля одного видео или GetCourse выключите переключатель плейлиста.')
            return
        if not self.folder.get().strip():
            self.notice('Выберите папку', 'Укажите папку для скачивания.')
            return
        if not binary_path('ffmpeg'):
            self.notice('Не найден FFmpeg', 'Запускайте программу из полной папки приложения.')
            return
        selected_folder = str(Path(self.folder.get().strip()).resolve())
        folder = str(Path(selected_folder) / detected_service)
        try:
            Path(folder).mkdir(parents=True, exist_ok=True)
        except OSError as error:
            self.notice('Не удалось открыть папку', str(error))
            return
        self.remember_folder(selected_folder)
        access = dict(self.access) if needs_getcourse_login(url) else ({'method': 'YouTube session'} if is_youtube and self.youtube_connected else None)
        if is_instagram:
            access = {'method': 'Instagram session'} if self.instagram_connected else None
        mode = {'Звук MP3': 'Только звук — MP3', 'Видео MKV': 'Видео — MKV', 'Видео WebM': 'Видео — WebM'}.get(self.mode.get(), 'Видео — MP4')
        from urllib.parse import parse_qs
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        if is_youtube:
            video_id = (query.get('v') or [parsed.path.strip('/').split('/')[-1]])[0]
            identity = ('youtube', 'playlist' if whole_playlist else 'video', query.get('list') if whole_playlist else video_id)
        elif is_instagram:
            identity = ('Instagram', parsed.path.rstrip('/').split('/')[-1])
        else:
            identity = (parsed.hostname, parsed.path, query.get('id') or parsed.query)
        save_description_text = is_instagram and self.save_instagram_description.get()
        description_format = self.instagram_description_format.get() if save_description_text else 'TXT'
        author_folder = is_instagram and self.instagram_author_folder.get()
        post_folder = is_instagram and (self.instagram_post_folder.get() or bool(profile_username(url)))
        profile_limit = {'Все публикации': 0, 'До 10 публикаций': 10, 'До 50 публикаций': 50, 'До 100 публикаций': 100}[self.instagram_profile_limit.get()] if is_instagram else 0
        key = repr((identity, os.path.normcase(folder), mode, self.quality.get(), whole_playlist, self.getcourse_scope.get() if self.tabs.get() == 'GetCourse' else self.instagram_scope.get() if is_instagram else '', save_description_text, description_format, author_folder, post_folder, profile_limit if profile_username(url) else None))
        if key in self.jobs_by_key:
            self.retry_job(self.jobs_by_key[key], auto_start)
            return
        index = self.next_row_id
        service = self.tabs.get()
        self.display_queue([{'title': url, 'service': service}], append=True)
        job = {'url': url, 'folder': folder, 'mode': mode, 'quality': self.quality.get(), 'access': access, 'playlist': whole_playlist, 'service': service, 'row': index, 'scope': self.getcourse_scope.get() if service == 'GetCourse' else self.instagram_scope.get() if service == 'Instagram' else 'Первое видео', 'rows': [index], 'save_description': save_description_text, 'description_format': description_format, 'author_folder': author_folder, 'post_folder': post_folder, 'profile_limit': profile_limit}
        self.jobs_by_key[key] = job
        self.jobs_by_row[index] = job
        self.pending_jobs.append(job)
        self.queue_count.set(f'{len(self.pending_jobs)} ожидают · {len(self.rows)} в списке')
        if auto_start and not self.busy:
            self.launch_next()

    def launch_next(self):
        if self.busy or self.queue_paused or not self.pending_jobs:
            return
        job = self.pending_jobs.pop(0)
        self.active_job = job
        self.active_run = object()
        self.active_rows = list(job['rows'])
        self.active_folder = job['folder']
        self.active_row = job['row']
        self.skip_current.clear()
        for row in job['rows']:
            self.row_phases[row] = 'queued'
        self.cancel.clear()
        self.progress.set(0)
        self.set_busy(True)
        self.status.set('Получаю информацию…')
        self.queue_count.set(f'1 скачивается · {len(self.pending_jobs)} ожидают')
        if job['row'] in self.rows:
            self.rows[job['row']][1].set('Получаю информацию…')
        self.refresh_row_controls()
        self.localize_ui()
        threading.Thread(target=self.worker, args=(job['url'], job['folder'], job['mode'], job['quality'], job['access'], job['playlist'], job['scope'], job.get('save_description', False), job.get('description_format', 'TXT'), self.active_run, job.get('author_folder', False), job.get('post_folder', False), job.get('profile_limit', 10)), daemon=True).start()

    def request_cancel(self):
        self.cancel.set()
        self.status.set('Отменяю загрузку. Текущая обработка файла может сначала завершиться.')
        self.cancel_button.configure(state='disabled')

    def retry_job(self, job, auto_start=True):
        if job is self.active_job or any(item is job for item in self.pending_jobs):
            self.status.set('Эта загрузка уже в очереди.')
            return
        if all(self.rows[index][1].get() == 'Скачано' for index in job['rows']):
            self.status.set('Этот файл уже скачан.')
            return
        if job['service'] == 'YouTube':
            job['access'] = {'method': 'YouTube session'} if self.youtube_connected else None
        if job['service'] == 'Instagram':
            job['access'] = {'method': 'Instagram session'} if self.instagram_connected else None
        if job['service'] == 'GetCourse':
            job['access'] = dict(self.access) if needs_getcourse_login(job['url']) else None
        for index in job['rows']:
            if self.rows[index][1].get() != 'Скачано':
                self.rows[index][1].set('В очереди')
                self.retry_buttons[index].grid_remove()
        self.pending_jobs.append(job)
        if auto_start and not self.busy:
            self.launch_next()

    def show_retry(self, index):
        if index in self.retry_buttons and index in self.jobs_by_row:
            self.retry_buttons[index].grid(row=0, column=4, padx=(0, 8), pady=5)

    def toggle_pause(self):
        if self.queue_paused:
            self.queue_paused = False
            self.pause_button.configure(text='Пауза')
            self.launch_next()
            if not self.busy:
                self.pause_button.configure(state='disabled')
        elif self.busy:
            self.paused_row = self.active_row
            self.queue_paused = True
            self.pause_requested = True
            self.cancel.set()
            self.pause_button.configure(text='Продолжить')
            self.status.set('Приостанавливаю загрузку…')

    def refresh_row_controls(self):
        for index, button in self.row_pause_controls.items():
            if index not in self.rows:
                continue
            active = self.busy and index == self.active_row and self.row_phases.get(index) not in ('done', 'error')
            paused = self.queue_paused and index == self.paused_row
            signature = (active, paused, self.skip_current.is_set())
            if self._ui_cache.get(('controls', index)) == signature:
                continue
            self._ui_cache[('controls', index)] = signature
            if active or paused:
                self.update_widget(button, text='Продолжить' if paused else 'Пауза', state='normal', image=self.command_icon('play' if paused else 'pause'))
            self.visible(button, active or paused, row=0, column=6, padx=(0,6), pady=5)
            cancel = self.row_cancel_controls[index]
            if active:
                self.update_widget(cancel, state='disabled' if self.skip_current.is_set() else 'normal')
            self.visible(cancel, active, row=0, column=7, padx=(0,6), pady=5)

    def cancel_video(self, index):
        if not self.busy or index != self.active_row:
            return
        self.skip_current.set()
        self.rows[index][1].set('Отменяю…')
        self.refresh_row_controls()
        self.localize_ui()

    def pause_video(self, index):
        if index == self.active_row or (self.queue_paused and index == self.paused_row):
            self.toggle_pause()
            self.refresh_row_controls()
            self.localize_ui()

    def clear_rows(self):
        for child in self.queue_panel.winfo_children():
            child.destroy()
        self.rows.clear()

    def display_queue(self, entries, append=False):
        self.empty_panel.grid_remove()
        self.queue_panel.grid(row=1, column=0, sticky='nsew', padx=12, pady=(0, 16))
        self.queue_count.set(f'{len(entries)} видео в очереди')
        offset = self.next_row_id if append else 0
        for local_index, entry in enumerate(entries):
            index = offset + local_index
            self.next_row_id = max(self.next_row_id, index + 1)
            card = ctk.CTkFrame(self.queue_panel, fg_color=COLORS['surface_high'], corner_radius=14)
            card.grid(row=index, column=0, sticky='ew', padx=5, pady=3)
            card.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(card, text=f'{index+1:03}', width=30, height=26, corner_radius=8, fg_color=COLORS['secondary_container'], text_color=COLORS['secondary'], font=(FONT_FAMILY, 11, 'bold')).grid(row=0, column=0, padx=(8, 10), pady=6)
            title = tk.StringVar(value=short_media_title((entry or {}).get('title') or 'Видео'))
            state = tk.StringVar(value='В очереди')
            title_label = self.label(card, '', textvariable=title, size=12, weight='bold', anchor='w', wraplength=280)
            title_label._i18n_user_content = True
            title_label.grid(row=0, column=1, sticky='ew', padx=(0, 10), pady=5)
            title_label.configure(wraplength=0)
            title_label.bind('<Enter>', lambda event, row=index: self.show_title_tooltip(row))
            title_label.bind('<Leave>', lambda event: self.hide_tooltip())
            card.bind(f'<{CONTEXT_BUTTON}>', lambda event, row=index: self.row_menu(event, row))
            for child in card.winfo_children():
                child.bind(f'<{CONTEXT_BUTTON}>', lambda event, row=index: self.row_menu(event, row))
            state_label = self.label(card, '', textvariable=state, size=12, color=COLORS['muted'], width=230, anchor='e')
            state_label.configure(width=185, anchor='e')
            state_label.grid(row=0, column=2, sticky='e', padx=(0, 10), pady=5)
            source = (entry or {}).get('service') or (self.active_job or {}).get('service') or self.tabs.get()
            badge = ctk.CTkLabel(card, text=source, height=22, width=74, corner_radius=7, text_color='#FFFFFF', fg_color={'GetCourse':'#013A4C','Instagram':'#C13584'}.get(source,'#D50000'), font=(FONT_FAMILY, 10, 'bold'))
            badge._fixed_source_theme = True
            badge.grid(row=0, column=3, padx=(0, 8), pady=5)
            self.rows[index] = (title, state, state_label)
            self.row_details[index] = self.label(card, '', size=11, color=COLORS['muted'], anchor='w')
            bar = ctk.CTkProgressBar(card, height=2, progress_color=COLORS['tertiary'], fg_color=COLORS['surface_high'])
            bar.set(0)
            bar.grid(row=2, column=0, columnspan=9, sticky='ew', padx=8)
            self.row_bars[index] = bar
            retry = self.button(card, 'Доскачать', lambda row=index: self.retry_job(self.jobs_by_row[row]), kind='outline', width=85, height=26)
            self.retry_buttons[index] = retry
            self.row_cards[index] = card
            delete = self.button(card, 'Удалить файл', lambda row=index: self.confirm_delete_files([row]), kind='outline', width=90, height=26)
            self.delete_buttons[index] = delete
            self.row_pause_controls[index] = self.button(card, 'Пауза', lambda row=index: self.pause_video(row), kind='outline', width=76, height=26)
            self.row_cancel_controls[index] = self.button(card, 'Отменить', lambda row=index: self.cancel_video(row), kind='outline', width=82, height=26)
            self.button(card, '…', lambda row=index: self.row_menu(None, row), kind='outline', width=26, height=26).grid(row=0, column=8, padx=(0, 6), pady=5)

    def worker(self, url, folder, mode, quality, access=None, whole_playlist=False, lesson_scope='Первое видео', save_description_text=False, description_format='TXT', run_id=None, instagram_author_folder=False, instagram_post_folder=False, instagram_profile_limit=10):
        run_id = run_id if run_id is not None else getattr(self, 'active_run', None)
        def emit(event):
            self.events.put((*event, run_id))
        current_index, total_count = 0, 1
        current_title = None
        last_sample = None
        smoothed_speed = 0.0
        telemetry_lock = threading.Lock()
        def hook(data):
            if self.skip_current.is_set():
                raise yt_dlp.utils.DownloadError('Скачивание отменено')
            if self.cancel.is_set():
                raise yt_dlp.utils.DownloadError('Скачивание отменено')
            if data.get('status') == 'downloading':
                nonlocal current_title, last_sample, smoothed_speed
                title = short_media_title((data.get('info_dict') or {}).get('title'))
                if title and title != current_title:
                    current_title = title
                    emit(('row', (current_index, title, 'Скачивание…', 'active')))
                total = data.get('total_bytes') or data.get('total_bytes_estimate') or 0
                percent = min(100, data.get('downloaded_bytes', 0) * 100 / total) if total else None
                if percent is None and data.get('fragment_count'):
                    percent = min(100, (data.get('fragment_index') or 0) * 100 / data['fragment_count'])
                # Fragment callbacks report burst speeds; show bytes/time over a
                # half-second sample instead, and paint telemetry at most twice/sec.
                now = time.monotonic()
                downloaded = data.get('downloaded_bytes', 0)
                stream = data.get('filename')
                with telemetry_lock:
                    if last_sample is None or last_sample[0] != stream or downloaded < last_sample[2]:
                        last_sample = (stream, now, downloaded)
                        smoothed_speed = 0.0
                        return
                    elapsed = now - last_sample[1]
                    if elapsed < .5:
                        return
                    measured = max(0, downloaded - last_sample[2]) / max(elapsed, .001)
                    smoothed_speed = measured if not smoothed_speed else .7 * smoothed_speed + .3 * measured
                    last_sample = (stream, now, downloaded)
                    eta = max(0, total - downloaded) / smoothed_speed if total and smoothed_speed else data.get('eta')
                    emit(('eta', (current_index, eta)))
                    emit(('progress', (current_index, percent, smoothed_speed / 1024 / 1024, total_count)))
            elif data.get('postprocessor') and data.get('status') in ('started', 'processing'):
                emit(('row', (current_index, None, 'Обработка файла…', 'active')))
        def downloader(options):
            cookie_source = options.pop('_cookies_source', None)
            youtube_auth = options.pop('_youtube_session', False)
            instagram_auth = options.pop('_instagram_session', False)
            instance = yt_dlp.YoutubeDL(options)
            instance.add_info_extractor(GetCourseRuPlayerIE())
            instance.add_info_extractor(ClipFlowInstagramIE())
            if youtube_auth:
                self.youtube_session.apply(instance.cookiejar)
            if instagram_auth:
                self.instagram_session.apply(instance.cookiejar)
            if cookie_source:
                instance.cookiejar.load(cookie_source, ignore_discard=True, ignore_expires=True)
            return instance
        try:
            if profile_username(url):
                import http.cookiejar
                jar = http.cookiejar.CookieJar()
                if (access or {}).get('method') == 'Instagram session':
                    self.instagram_session.apply(jar)
                emit(('row', (0, 'Instagram / ' + profile_username(url), 'Получаю список публикаций…', 'active')))
                posts = profile_posts(url, instagram_profile_limit, jar, self.cancel)
                if self.cancel.is_set():
                    raise yt_dlp.utils.DownloadError('Скачивание отменено')
                if not posts:
                    raise yt_dlp.utils.DownloadError('В профиле нет доступных публикаций.')
                emit(('profile_posts', posts))
                emit(('download_started', url))
                emit(('row', (0, None, 'Добавлено в очередь', 'done')))
                emit(('done', f'{len(posts)} публикаций добавлено в очередь'))
                return
            entries = [{'url': url, 'title': 'Получаю название видео…'}]
            playlist_title = ''
            instagram = is_instagram_url(url)
            lesson_multiple = not instagram and lesson_scope != 'Первое видео' and not whole_playlist
            if lesson_multiple:
                meta_options = download_options(folder, mode, quality, hook, access)
                meta_options.update(noplaylist=False, extract_flat='in_playlist', skip_download=True)
                meta_options.pop('playlist_items', None)
                meta_options.pop('postprocessors', None)
                with downloader(meta_options) as ydl:
                    info = ydl.extract_info(url, download=False)
                entries = [entry for entry in (info.get('entries', []) if info.get('_type') == 'playlist' else [info]) if entry]
                lesson_title = info.get('title') or 'Урок GetCourse'
                for number, entry in enumerate(entries, 1):
                    entry['url'] = entry.get('url') or entry.get('webpage_url') or url
                    entry['lesson_number'] = number
                    entry['title'] = short_media_title((entry.get('title') or lesson_title) + (f' - Видео {number}' if len(entries) > 1 else ''))
                if lesson_scope == 'Выбрать видео':
                    gate, result = threading.Event(), []
                    emit(('select_videos', (entries, gate, result)))
                    while not gate.wait(.2):
                        if self.cancel.is_set():
                            raise yt_dlp.utils.DownloadError('Скачивание отменено')
                    if self.cancel.is_set():
                        raise yt_dlp.utils.DownloadError('Скачивание отменено')
                    entries = [entries[index] for index in result]
                if not entries:
                    raise yt_dlp.utils.DownloadError('На странице нет доступных видео.')
            if instagram:
                meta_options = download_options(folder, mode, quality, hook, access)
                meta_options.update(noplaylist=False, skip_download=True)
                meta_options.pop('playlist_items', None)
                with downloader(meta_options) as ydl:
                    info = ydl.extract_info(url, download=False, process=False)
                raw_entries = list(info.get('entries') or []) if info.get('_type') == 'playlist' else [info]
                entries = []
                for number, item in enumerate(raw_entries, 1):
                    if not item:continue
                    item = dict(item)
                    if not item.get('description') and info.get('description'):
                        item['description'] = info['description']
                    photo = item.get('_clipflow_photo', False)
                    if lesson_scope == 'Только фото' and not photo:continue
                    if lesson_scope == 'Только видео' and photo:continue
                    if mode == 'Только звук — MP3' and photo:continue
                    item['title'] = media_title(item)
                    entries.append({'url': url, 'title': item['title'], 'media_info': item, 'media_number': number})
                if instagram_author_folder:
                    folder = str(Path(folder) / author_directory(info, [e['media_info'] for e in entries]))
                    Path(folder).mkdir(parents=True, exist_ok=True)
                    emit(('folder', folder))
                if instagram_post_folder and entries:
                    folder = str(Path(folder) / post_directory(info, url, raw_entries))
                    Path(folder).mkdir(parents=True, exist_ok=True)
                    emit(('folder', folder))
                if not entries:
                    raise yt_dlp.utils.DownloadError('В публикации нет выбранного типа файлов. Для фотографий выберите «Видео и фото (MP4)» и «Всё» или «Только фото».')
            if whole_playlist:
                meta_options = download_options(folder, mode, quality, hook, access)
                meta_options.update(noplaylist=False, extract_flat='in_playlist', skip_download=True)
                meta_options.pop('playlist_items', None)
                meta_options.pop('postprocessors', None)
                with downloader(meta_options) as ydl:
                    info = ydl.extract_info(youtube_playlist_url(url), download=False)
                    entries = list(info.get('entries') or [])
                if self.cancel.is_set():
                    raise yt_dlp.utils.DownloadError('Скачивание отменено')
                if not entries:
                    raise yt_dlp.utils.DownloadError('Плейлист пуст, закрыт или недоступен.')
                playlist_title = info.get('title') or 'Плейлист'
                playlist_id = parse_qs(urlparse(youtube_playlist_url(url)).query)['list'][0]
                folder = str(Path(folder) / ('Playlist [' + playlist_id + ']'))
                Path(folder).mkdir(parents=True, exist_ok=True)
                emit(('folder', folder))
            total_count = len(entries)
            emit(('queue', entries))
            completed, failures = 0, []
            for current_index, entry in enumerate(entries):
                if self.cancel.is_set():
                    raise yt_dlp.utils.DownloadError('Скачивание отменено')
                if not entry:
                    entry = {}
                title = short_media_title(entry.get('title') or 'Недоступное видео')
                current_title = None
                emit(('row', (current_index, title, 'Получаю информацию…', 'active')))
                try:
                    video_url = entry.get('url') or ('https://www.youtube.com/watch?v=' + entry['id'] if entry.get('id') else None)
                    if not video_url:
                        raise yt_dlp.utils.DownloadError('Видео недоступно')
                    options = download_options(folder, mode, quality, hook, access)
                    if not whole_playlist and not ((urlparse(video_url).hostname or '').endswith('youtube.com') or urlparse(video_url).hostname == 'youtu.be'):
                        options['outtmpl'] = '%(title).56s.%(ext)s'
                    if whole_playlist:
                        options['outtmpl'] = f'{current_index+1:03d} - %(title).50s.%(ext)s'
                    elif lesson_multiple and len(entries) > 1:
                        options['outtmpl'] = f'{entry["lesson_number"]:03d} - %(title).50s.%(ext)s'
                    if instagram:
                        options['outtmpl'] = (f'{entry["media_number"]:02d}.%(ext)s' if instagram_post_folder
                                              else f'{entry["media_number"]:02d} - %(title).50s.%(ext)s')
                    with downloader(options) as ydl:
                        if instagram:
                            info = dict(entry['media_info'])
                            title = info['title']
                            current_title = title
                            emit(('row', (current_index, title, 'Скачивание…', 'active')))
                            emit(('download_started', url))
                            info = download_photo(ydl, info, folder, hook) if info.get('_clipflow_photo') else ydl.process_ie_result(info, download=True)
                        elif lesson_multiple:
                            info = ydl.extract_info(video_url, download=False)
                            info['title'] = short_media_title(entry['title'])
                            current_title = info['title']
                            emit(('row', (current_index, current_title, 'Скачивание…', 'active')))
                            emit(('progress', (current_index, 0, 0, total_count)))
                            emit(('download_started', url))
                            info = ydl.process_ie_result(info, download=True)
                        else:
                            info = ydl.extract_info(video_url, download=False)
                            if not info:
                                raise yt_dlp.utils.DownloadError('Видео недоступно')
                            title = short_media_title(info.get('title') or title)
                            info['title'] = title
                            current_title = title
                            emit(('row', (current_index, title, 'Скачивание…', 'active')))
                            emit(('progress', (current_index, 0, 0, total_count)))
                            emit(('download_started', url))
                            info = ydl.process_ie_result(info, download=True)
                        if not info or (info.get('_type') == 'playlist' and not any(info.get('entries') or [])):
                            raise yt_dlp.utils.DownloadError('На странице нет доступного видео. Проверьте вход GetCourse.')
                        clean_download_sidecars(info, ydl, folder)
                        paths = completed_media_paths(info, ydl, folder)
                        if instagram and save_description_text:
                            paths += save_description(info, paths, folder, description_format)
                        emit(('files', (current_index, paths)))
                    title = info.get('title') or title
                    emit(('row', (current_index, title, 'Скачано', 'done')))
                    completed += 1
                except Exception as error:
                    if self.skip_current.is_set():
                        self.skip_current.clear()
                        emit(('row', (current_index, title, 'Отменено', 'error')))
                        continue
                    if self.cancel.is_set():
                        emit(('row', (current_index, None, 'Отменено', 'error')))
                        raise
                    if not whole_playlist and not lesson_multiple and not instagram:
                        raise
                    failures.append((current_index+1, str(error)))
                    emit(('row', (current_index, None, 'Не удалось скачать', 'error')))
                emit(('overall', (current_index+1) / total_count))
            if failures:
                emit(('summary', (completed, total_count, failures)))
            else:
                emit(('done', f'{completed} из {total_count} ' + ('файлов' if instagram else 'видео') + (' · ' + playlist_title if playlist_title else '')))
        except Exception as error:
            text = access_error_message(error, access)
            emit(('cancelled' if self.cancel.is_set() else 'error', text))

    def poll(self):
        # Schedule after painting: Tk idle redraws cannot re-enter this batch.
        self._poll_after = None
        try:
            with atomic_redraw(self.root):
                self._poll_updates()
        finally:
            self._poll_after = self.root.after(120, self.poll)

    def _poll_updates(self):
        import time
        connected = self.youtube_connected
        if time.monotonic() >= getattr(self, '_next_youtube_refresh', 0):
            self._next_youtube_refresh = time.monotonic() + 1
            connected = bool(self.youtube_session.saved())
        if connected != self.youtube_connected:
            self.youtube_connected = connected
            self.youtube_status.set('YouTube: сессия сохранена' if connected else 'YouTube: вход не выполнен')
            if connected:
                self.status.set('YouTube: сессия сохранена')
        ig_connected = self.instagram_connected
        if time.monotonic() >= getattr(self, '_next_instagram_refresh', 0):
            self._next_instagram_refresh = time.monotonic() + 1
            ig_connected = bool(self.instagram_session.saved())
        if ig_connected != self.instagram_connected:
            self.instagram_connected = ig_connected
            self.instagram_status.set('Instagram: сессия сохранена' if ig_connected else 'Instagram: вход не выполнен')
        pending = []
        while True:
            try:
                event = self.events.get_nowait()
                pending.append(event)
            except queue.Empty:
                break
        structural = connected != getattr(self, '_auth_controls_connected', None)
        for event in coalesce_updates(pending):
            kind, value = event[:2]
            if len(event) == 3 and event[2] is not self.active_run:
                continue
            if kind not in ('progress', 'eta', 'overall'):
                structural = True
            if kind == 'quality_result':
                service, request, heights, error = value
                context = self.contexts[service]
                if request != context.get('quality_request'):continue
                context['quality_pending'] = False
                self.refresh_download_buttons()
                values = ['Лучшее доступное']
                for height in heights:
                    label = '2160p (4K)' if height == 2160 else f'{height}p'
                    QUALITY[label] = height
                    values.append(label)
                context['quality_box'].configure(values=values)
                context['quality_box']._i18n_values = values
                context['quality_status'].set(error or ('Качество проверено' if heights else 'Нет вариантов качества'))
                if not error and self.auto_download.get():
                    context['quality'].set('Лучшее доступное')
                    previous = self.tabs.get()
                    with self.redraw_transaction():
                        self.tabs.set(service)
                        self.activate_tab()
                        try:
                            self.start(prefer_queue=False)
                        finally:
                            self.tabs.set(previous)
                            self.activate_tab()
            elif kind == 'instagram_auth_error':
                self.notice('Instagram', value)
            elif kind == 'youtube_auth':
                action, result = value
                if action == 'connected':
                    self.youtube_connected = True
                    self.youtube_status.set('YouTube: сессия сохранена')
                    self.status.set('YouTube: сессия сохранена')
                    if hasattr(self, 'youtube_dialog') and self.youtube_dialog.winfo_exists():
                        self.youtube_dialog.destroy()
                elif action == 'opened':
                    self.status.set('Окно входа открыто. Войдите в аккаунт на YouTube.')
                elif action == 'logout':
                    self.youtube_connected = False
                    self.youtube_status.set('YouTube: вход не выполнен')
                    for job in self.pending_jobs:
                        if job['service'] == 'YouTube':
                            job['access'] = None
                else:
                    self.notice('Вход YouTube', result)
            elif kind == 'select_videos':
                self.select_lesson_videos(*value)
            elif kind == 'profile_posts':
                if self.active_job:
                    for post_url in value:
                        key = ('profile-post', post_url, self.active_job['folder'], self.active_job['mode'], self.active_job['quality'], self.active_job['scope'], self.active_job.get('save_description'), self.active_job.get('description_format'), self.active_job.get('author_folder'))
                        if key in self.jobs_by_key:
                            continue
                        index = self.next_row_id
                        self.display_queue([{'title': post_url, 'service': 'Instagram'}], append=True)
                        job = dict(self.active_job, url=post_url, row=index, rows=[index], post_folder=True)
                        job.pop('resolved_folder', None)
                        self.jobs_by_key[key] = job
                        self.jobs_by_row[index] = job
                        self.pending_jobs.append(job)
            elif kind == 'queue':
                if self.active_job:
                    first = self.active_job['row']
                    previous_rows = self.active_job['rows']
                    self.active_rows = [first]
                    if value:
                        self.rows[first][0].set(short_media_title((value[0] or {}).get('title') or 'Видео'))
                    for number, entry in enumerate(value[1:], 1):
                        if number < len(previous_rows):
                            index = previous_rows[number]
                            self.rows[index][0].set(short_media_title((entry or {}).get('title') or 'Видео'))
                        else:
                            index = self.next_row_id
                            self.display_queue([entry], append=True)
                            self.jobs_by_row[index] = self.active_job
                        self.active_rows.append(index)
                    self.active_job['rows'] = list(self.active_rows)
                    self.queue_count.set(f'1 скачивается · {len(self.pending_jobs)} ожидают')
                else:
                    self.display_queue(value)
            elif kind == 'files':
                index, paths = value
                if self.active_job and index < len(self.active_rows):
                    index = self.active_rows[index]
                if index in self.rows:
                    self.row_files[index] = paths
                    if paths:
                        self.delete_buttons[index].grid_remove()
            elif kind == 'download_started':
                if self.active_job:
                    context = self.contexts[self.active_job['service']]
                    if context['url'].get().strip() == value:
                        context['url'].set('')
            elif kind == 'folder':
                self.active_folder = value
                if self.active_job:
                    self.active_job['resolved_folder'] = value
            elif kind == 'row':
                index, title, text, state = value
                if self.active_job and index < len(self.active_rows):
                    index = self.active_rows[index]
                if index in self.rows:
                    row_title, row_state, label = self.rows[index]
                    if self.row_phases.get(index) in ('done', 'error') and state == 'active':
                        continue
                    self.row_phases[index] = state
                    if state == 'active':
                        self.active_row = index
                    if title:
                        row_title.set(short_media_title(title))
                    row_state.set(text)
                    if state == 'done':
                        self.row_bars[index].set(1)
                        self.row_details[index].configure(text='')
                    if state == 'error':
                        self.show_retry(index)
                    elif index in self.retry_buttons:
                        self.retry_buttons[index].grid_remove()
                    label.configure(text_color=COLORS['error'] if state == 'error' else COLORS['tertiary'] if state == 'done' else COLORS['secondary'])
            elif kind == 'eta':
                index, eta = value
                if self.active_job and index < len(self.active_rows):
                    index = self.active_rows[index]
                self.row_eta[index] = eta
                if index in self.row_details and eta is not None:
                    self.row_details[index].configure(text=('Осталось: ' if self.language == 'ru' else 'Remaining: ') + f'{int(eta)//60}:{int(eta)%60:02}')
            elif kind == 'progress' and not self.cancel.is_set():
                index, percent, speed, total = value
                local_index = index
                if self.active_job and index < len(self.active_rows):
                    index = self.active_rows[index]
                if self.row_phases.get(index) in ('done', 'error'):
                    continue
                self.row_phases[index] = 'active'
                self.active_row = index
                text = (f'{percent:.0f}%' if percent is not None else 'Скачивание…') + f'  ·  {speed:.1f} МБ/с'
                eta = self.row_eta.get(index)
                if eta is not None:
                    text += f'  ·  {int(eta)//60}:{int(eta)%60:02}'
                if index in self.rows:
                    if self.rows[index][1].get() != text:
                        self.rows[index][1].set(text)
                    if self.language == 'en':
                        self.rows[index][2]._label.configure(textvariable='', text=self.translate(text))
                    if percent is not None:
                        self.row_bars[index].set(percent / 100)
                footer_text = f'{"Файл" if self.active_job and self.active_job["service"] == "Instagram" else "Видео"} {local_index+1} из {total}  ·  {text}'
                self.status.set(footer_text)
                if self.language == 'en':
                    self.status_label._label.configure(textvariable='', text=self.translate(footer_text))
                if percent is not None:
                    self.progress.set((local_index + percent/100) / total)
            elif kind == 'overall':
                self.progress.set(value)
            elif kind in ('done', 'error', 'cancelled', 'summary'):
                self.set_busy(False)
                if kind != 'cancelled':
                    self.pause_requested = False
                if kind == 'done':
                    self.progress.set(1)
                    self.status.set('Готово: ' + value)
                    self.queue_count.set('Загрузка завершена')
                    if self.active_job and (self.active_job['access'] or {}).get('method') == 'Email и пароль' and self.access.get('email') == self.active_job['access']['email']:
                        self.profile_status.set('Вход подтверждён: ' + self.active_job['access']['email'])
                elif kind == 'summary':
                    completed, total, failures = value
                    self.status.set(f'Завершено: скачано {completed} из {total}. Ошибок: {len(failures)}.')
                    self.queue_count.set(f'{completed} скачано · {len(failures)} с ошибками')
                    details = '\n\n'.join(f'Видео {index}: {error}' for index, error in failures[:8])
                    self.error_log.append(details)
                elif kind == 'cancelled':
                    paused = self.pause_requested
                    self.status.set('На паузе' if paused else 'Отменено. Повторный запуск продолжит частичные файлы и пропустит готовые.')
                    for row_index in (self.active_rows if self.active_job else list(self.rows)):
                        _, state, label = self.rows[row_index]
                        if state.get() != 'Скачано' and state.get() != 'Не удалось скачать':
                            state.set('На паузе' if paused else 'Отменено')
                            if not paused:
                                self.show_retry(row_index)
                            elif row_index in self.retry_buttons:
                                self.retry_buttons[row_index].grid_remove()
                            label.configure(text_color=COLORS['muted'])
                    if paused and self.active_job:
                        self.pending_jobs.insert(0, self.active_job)
                        self.pause_requested = False
                else:
                    self.status.set('Не удалось скачать. Проверьте ссылку, доступ или подключение.')
                    for row_index in (self.active_rows if self.active_job else list(self.rows)):
                        _, state, label = self.rows[row_index]
                        if state.get() != 'Скачано':
                            state.set('Не удалось скачать')
                            self.show_retry(row_index)
                            label.configure(text_color=COLORS['error'])
                    self.error_log.append(str(value))
                    for row in (self.active_rows if self.active_job else list(self.rows)):
                        if row in self.row_details:
                            self.row_details[row].configure(text=str(value).splitlines()[0][:100])
        if self.active_job and not self.busy:
            self.active_job = None
            self.active_run = None
            self.launch_next()
        if structural:
            self.refresh_row_controls()
            self.refresh_auth_controls()
            self.refresh_list()
            self.localize_ui()

    def remove_download_row(self, index):
        job = self.jobs_by_row.get(index)
        if job is not None and job is self.active_job:
            self.status.set('Дождитесь завершения текущей задачи.')
            return
        if job:
            self.pending_jobs = [item for item in self.pending_jobs if item is not job]
            job['rows'] = [row for row in job['rows'] if row != index]
            if not job['rows']:
                self.jobs_by_key = {key: value for key, value in self.jobs_by_key.items() if value is not job}
            elif job['row'] == index:
                job['row'] = job['rows'][0]
        card = self.row_cards.pop(index, None)
        if card:
            card.destroy()
        for mapping in (self.rows, self.row_files, self.delete_buttons, self.retry_buttons, self.jobs_by_row, self.row_pause_controls, self.row_cancel_controls, self.row_bars, self.row_details, self.row_eta, self.row_phases):
            mapping.pop(index, None)
        if index == self.paused_row:
            self.paused_row = None
            self.queue_paused = False
        self.queue_count.set(f'{len(self.pending_jobs)} ожидают · {len(self.rows)} в списке')
        if not self.rows:
            self.queue_panel.grid_remove()
            self.empty_panel.grid()

    def clear_download_list(self):
        for index in list(self.rows):
            self.remove_download_row(index)

    def confirm_delete_files(self, indexes):
        paths = sorted({path for index in indexes for path in self.row_files.get(index, [])})
        if not paths:
            return
        dialog = ctk.CTkToplevel(self.root)
        dialog.title('Удаление файлов')
        dialog.geometry('650x340')
        dialog.configure(fg_color=COLORS['surface'])
        dialog.transient(self.root)
        dialog.grab_set()
        self.label(dialog, 'Удалить эти файлы с диска? Это действие нельзя отменить.', size=16, weight='bold', wraplength=595).pack(anchor='w', padx=24, pady=20)
        listing = ctk.CTkTextbox(dialog, fg_color=COLORS['surface_high'], text_color=COLORS['text'])
        listing.pack(fill='both', expand=True, padx=24)
        listing.insert('1.0', '\n'.join(paths))
        listing._i18n_user_content = True
        listing.configure(state='disabled')
        actions = ctk.CTkFrame(dialog, fg_color='transparent')
        actions.pack(fill='x', padx=24, pady=18)
        def confirmed():
            try:
                for path in paths:
                    Path(path).unlink(missing_ok=True)
            except OSError as error:
                self.notice('Не удалось удалить файл', str(error))
                return
            for index in indexes:
                if index in self.rows:
                    self.rows[index][1].set('Файл удалён')
                    self.row_files.pop(index, None)
                    self.delete_buttons[index].grid_remove()
                    self.show_retry(index)
            dialog.destroy()
        self.button(actions, 'Отмена', dialog.destroy, kind='outline', width=110).pack(side='right')
        self.button(actions, 'Удалить', confirmed, width=110).pack(side='left')
        self.localize_ui()

    def translate(self, text):
        TRANSLATIONS.update(PROGRESS_TRANSLATIONS)
        if self.language != 'en' or not isinstance(text, str):
            return text
        if text in TRANSLATIONS:
            return TRANSLATIONS[text]
        # Translate known fragments in dynamic statuses, leaving names and URLs intact.
        if not hasattr(self, '_translation_pattern'):
            self._translation_pattern = re.compile('|'.join(re.escape(key) for key in sorted(TRANSLATIONS, key=len, reverse=True)))
        return self._translation_pattern.sub(lambda match: TRANSLATIONS[match.group(0)], text)

    def localize_ui(self):
        global UI_LANGUAGE
        UI_LANGUAGE = self.language
        def visit(widget):
            if getattr(widget, '_i18n_user_content', False):
                return
            if widget is getattr(self, 'filter_box', None):
                for source, button in widget._buttons_dict.items():
                    self.update_widget(button, text=self.translate(source))
            if isinstance(widget, ctk.CTkLabel):
                variable = getattr(widget, '_i18n_variable', None) or widget.cget('textvariable')
                if variable:
                    widget._i18n_variable = variable
                    source = self.root.getvar(str(variable))
                    if self.language == 'ru':
                        if str(widget._label.cget('textvariable')) != str(variable):
                            widget._label.configure(textvariable=variable)
                    else:
                        rendered = self.translate(source)
                        if widget._label.cget('text') != rendered or widget._label.cget('textvariable'):
                            widget._label.configure(textvariable='', text=rendered)
                else:
                    caption(widget)
            elif isinstance(widget, (ctk.CTkButton, ctk.CTkCheckBox, ctk.CTkSwitch)):
                caption(widget)
            elif isinstance(widget, ctk.CTkOptionMenu):
                if not getattr(widget, '_i18n_user_values', False):
                    original = getattr(widget, '_i18n_values', widget.cget('values'))
                    widget._i18n_values = original
                    values = [self.translate(value) for value in original]
                    if widget.cget('values') != values:
                        widget.configure(values=values)
                    command = widget._command
                    if not getattr(command, '_i18n_wrapper', False):
                        def selected(value, widget=widget, original=original, command=command):
                            source = next((item for item in original if self.translate(item) == value), value)
                            if widget._variable is not None:
                                widget._variable.set(source)
                            if command:
                                command(source)
                            self.localize_ui()
                        selected._i18n_wrapper = True
                        widget.configure(command=selected)
                value = widget._variable.get() if widget._variable is not None else widget.get()
                rendered = self.translate(value)
                if widget._text_label.cget('text') != rendered:
                    widget._text_label.configure(text=rendered)
            if isinstance(widget, (ctk.CTk, ctk.CTkToplevel)):
                current = widget.title()
                source = getattr(widget, '_i18n_title', current) if current == getattr(widget, '_i18n_rendered_title', None) else current
                widget._i18n_title = source
                widget._i18n_rendered_title = self.translate(source)
                if current != widget._i18n_rendered_title:
                    widget.title(widget._i18n_rendered_title)
            if isinstance(widget, ctk.CTkTextbox):
                current = widget.get('1.0', 'end-1c')
                source = getattr(widget, '_i18n_source', current) if current == getattr(widget, '_i18n_rendered', None) else current
                translated = self.translate(source)
                widget._i18n_source, widget._i18n_rendered = source, translated
                if current != translated:
                    state = widget.cget('state')
                    widget.configure(state='normal')
                    widget.delete('1.0', 'end')
                    widget.insert('1.0', translated)
                    widget.configure(state=state)
            for child in widget.winfo_children():
                visit(child)
        def caption(widget):
            current = widget.cget('text')
            source = getattr(widget, '_i18n_source', current) if current == getattr(widget, '_i18n_rendered', None) else current
            widget._i18n_source = source
            translated = self.translate(source)
            widget._i18n_rendered = translated
            if current != translated:
                widget.configure(text=translated)
        visit(self.root)

    def instagram_scope_changed(self, value):
        if value == 'Только фото':
            self.contexts['Instagram']['mode'].set('Видео и фото (MP4)')
        self.contexts['Instagram']['mode_box'].configure(state='disabled' if value == 'Только фото' else 'normal')
        self.contexts['Instagram']['quality_box'].configure(state='disabled' if value == 'Только фото' or self.contexts['Instagram']['mode'].get() == 'Звук MP3' else 'normal')

    def signin_instagram(self):
        self.status.set('Открываю окно входа Instagram…')
        def run():
            try:self.instagram_session.launch(self.language)
            except Exception as error:self.events.put(('instagram_auth_error', str(error)))
        threading.Thread(target=run, daemon=True).start()

    def logout_instagram(self):
        self.instagram_session.logout()
        self.instagram_connected = False
        self.instagram_status.set('Instagram: вход не выполнен')
        for job in self.pending_jobs:
            if job['service'] == 'Instagram':job['access'] = None
        self.refresh_auth_controls()

    def signin_youtube(self):
        self.status.set('Открываю встроенное окно входа YouTube…')
        self.youtube_auth_action('launch')

    def youtube_auth_action(self, action):
        def run():
            try:
                if action == 'launch':
                    self.youtube_session.launch(self.language)
                    self.events.put(('youtube_auth', ('opened', None)))
                elif action == 'logout':
                    self.youtube_session.logout()
                    self.events.put(('youtube_auth', ('logout', None)))
                else:
                    self.youtube_session.capture()
                    self.events.put(('youtube_auth', ('connected', None)))
            except Exception as error:
                self.events.put(('youtube_auth', ('error', str(error))))
        if action == 'capture':
            self.status.set('Проверяю вход…')
        threading.Thread(target=run, daemon=True).start()

    def logout_youtube(self):
        self.youtube_connected = False
        self.youtube_auth_action('logout')

    def toggle_completed(self):
        self.show_completed = not self.show_completed
        self.refresh_list()

    def reflow_controls(self, panel, width):
        narrow = width < 900
        if getattr(panel, '_compact_layout', None) == narrow:
            return
        panel._compact_layout = narrow
        for child in panel.winfo_children():
            info = child.grid_info()
            if not info:
                continue
            original = getattr(child, '_layout_original', None)
            if original is None:
                original = child._layout_original = dict(info)
            if int(original['column']) == 2:
                child.grid_configure(row=3 if narrow else int(original['row']), column=int(original['row']) if narrow else 2, padx=(0 if int(original['row']) == 0 else (24, 0)) if narrow else (24, 0), pady=(6, 0) if narrow else original['pady'])

    def refresh_auth_controls(self):
        # Instagram account UI is temporarily hidden, implementation is retained.
        self.visible(self.instagram_auth_row, False)
        self._auth_controls_connected = self.youtube_connected
        self.visible(self.youtube_login_button, not self.youtube_connected)

    @staticmethod
    def visible(widget, value, **grid):
        mapped = bool(widget.winfo_manager())
        if value and not mapped:
            widget.grid(**grid)
        elif not value and mapped:
            widget.grid_remove()

    @staticmethod
    def update_widget(widget, **changes):
        needed = {key:value for key,value in changes.items() if widget.cget(key) != value}
        if needed:
            widget.configure(**needed)

    def build_menu(self, header):
        bar = ctk.CTkFrame(header, fg_color='transparent')
        bar.grid(row=1, column=1, columnspan=4, sticky='w', pady=(6, 0))
        for name in ('Загрузки', 'Вид', 'Аккаунты', 'Настройки', 'Справка'):
            button = self.button(bar, name, lambda n=name: self.open_app_menu(n), kind='outline', width=95, height=28)
            button.pack(side='left', padx=(0, 5))
            button.configure(border_width=0)
        self.root.bind(f'<{MODIFIER}-n>', lambda event: self.add_links_dialog())
        self.root.bind(f'<{MODIFIER}-comma>', lambda event: self.show_settings())
        self.root.bind('<F1>', lambda event: self.show_help())

    def popup_commands(self, commands, x=None, y=None):
        menu = tk.Menu(self.root, tearoff=False, bg='#28282D', fg='#F2F2F5', activebackground='#414149', activeforeground='white', font=(FONT_FAMILY, 11), bd=0)
        for title, command in commands:
            if title is None:
                menu.add_separator()
            else:
                menu.add_command(label=self.translate(title), command=command)
        menu.tk_popup(x or self.root.winfo_pointerx(), y or self.root.winfo_pointery())
        menu.grab_release()

    def open_app_menu(self, name):
        menus = {
            'Загрузки': [('Добавить ссылку', lambda: self.url_entry.focus_set()), ('Добавить несколько ссылок', self.add_links_dialog), (None, None), ('Приостановить все', self.pause_all), ('Продолжить все', self.resume_all), ('Очистить завершённые', self.clear_completed), ('Очистить список', self.clear_download_list), (None, None), ('Удалить все файлы', lambda: self.confirm_delete_files(list(self.row_files)))],
            'Вид': [('Компактный список', lambda: self.set_list_mode(False)), ('Показывать завершённые', self.toggle_completed), ('Подробный список', lambda: self.set_list_mode(True)), ('Все', lambda: self.set_filter('Все')), ('Активные', lambda: self.set_filter('Активные')), ('Завершённые', lambda: self.set_filter('Завершённые')), ('Ошибки', lambda: self.set_filter('Ошибки')), ('Масштаб интерфейса', self.show_settings)],
            'Аккаунты': [ ('YouTube', lambda: self.select_account('YouTube')), ('GetCourse', lambda: self.select_account('GetCourse'))],
            'Настройки': [('Общие', self.show_settings), ('Скачивание', self.show_settings), ('Язык интерфейса', self.show_settings)],
            'Справка': [('Как пользоваться', self.show_help), ('Горячие клавиши', self.show_help), ('Журнал ошибок', self.show_errors), ('О ClipFlow', self.show_about)]}
        self.popup_commands(menus[name])

    def select_account(self, service):
        self.tabs.set(service)
        self.activate_tab()
        if service == 'Instagram':
            if not self.instagram_connected:self.signin_instagram()
        elif service == 'GetCourse':
            self.configure_access()
        elif not self.youtube_connected:
            self.signin_youtube()

    def pause_all(self):
        if not self.queue_paused:
            self.toggle_pause()

    def resume_all(self):
        if self.queue_paused:
            self.toggle_pause()
        else:
            self.launch_next()

    def clear_completed(self):
        for index, (_, state, _) in list(self.rows.items()):
            if state.get() == 'Скачано':
                self.remove_download_row(index)

    def set_filter(self, value):
        self.list_filter.set(value)
        self.refresh_list()

    def set_list_mode(self, detailed):
        self.detailed_list = detailed
        self.save_settings()
        self.refresh_list()

    def refresh_list(self):
        counts = {'Все': len(self.rows), 'Активные': 0, 'Завершённые': 0, 'Ошибки': 0}
        for index, (title, state, _) in self.rows.items():
            text = state.get()
            category = 'Завершённые' if text == 'Скачано' else 'Ошибки' if text in ('Не удалось скачать', 'Отменено') else 'Активные'
            counts[category] += 1
            card = self.row_cards[index]
            if self.list_filter.get() in ('Все', category) and (self.show_completed or category != 'Завершённые'):
                self.visible(card, True)
            else:
                self.visible(card, False)
            label = next((child for child in card.winfo_children() if getattr(child, '_i18n_user_content', False)), None)
            if label:
                available = max(130, card.winfo_width() - (550 if index == self.active_row and self.busy else 350))
                full = short_media_title(title.get())
                if self.detailed_list and not self.row_details[index].cget('text'):
                    paths = self.row_files.get(index)
                    self.row_details[index].configure(text=str(paths[0]) if paths else '')
                if not hasattr(self, '_row_title_font'):
                    self._row_title_font = ctk.CTkFont(family=FONT_FAMILY, size=12, weight='bold')
                font = self._row_title_font
                short = full
                while len(short) > 8 and font.measure(short) > available:
                    short = short[:-1]
                rendered = short + ('…' if short != full else '')
                if label._label.cget('text') != rendered or label._label.cget('textvariable'):
                    label._label.configure(textvariable='', text=rendered)
            if self.detailed_list:
                self.visible(self.row_details[index], True, row=1, column=1, columnspan=7, sticky='ew', pady=(0,6))
            else:
                self.visible(self.row_details[index], False)
        caption = ' · '.join(f'{self.translate(key)}: {value}' for key, value in counts.items())
        if self.queue_count.get() != caption:
            self.queue_count.set(caption)

    def hide_tooltip(self):
        if getattr(self, '_tooltip', None):
            self._tooltip.destroy()
            self._tooltip = None

    def refresh_download_buttons(self):
        for context in self.contexts.values():
            button = context.get('start_button')
            if button:
                enabled = supported_url(context['url'].get().strip()) and not context.get('quality_pending')
                self.update_widget(button, state='normal' if enabled else 'disabled', fg_color=COLORS['primary_action'] if enabled else COLORS['outline_variant'])

    def show_download_tooltip(self):
        self.hide_tooltip()
        tip = self._tooltip = ctk.CTkToplevel(self.root)
        tip.overrideredirect(True)
        tip.geometry(f'+{self.root.winfo_pointerx()+12}+{self.root.winfo_pointery()+18}')
        text = 'Проверяю качество…' if self.contexts[self.tabs.get()].get('quality_pending') else 'Добавить в очередь' if self.busy else 'Скачать'
        self.label(tip, self.translate(text), size=12).pack(padx=10, pady=6)

    def show_title_tooltip(self, index):
        self.hide_tooltip()
        if index not in self.rows:
            return
        tip = self._tooltip = ctk.CTkToplevel(self.root)
        tip.overrideredirect(True)
        tip.geometry(f'+{self.root.winfo_pointerx()+12}+{self.root.winfo_pointery()+18}')
        self.label(tip, self.rows[index][0].get(), size=12, wraplength=600).pack(padx=10, pady=6)

    def row_menu(self, event, index):
        commands = [('Открыть папку', lambda: self.open_row_folder(index)), ('Копировать название', lambda: self.copy_text(self.rows[index][0].get()))]
        if index in self.jobs_by_row:
            commands.append(('Повторить', lambda: self.retry_job(self.jobs_by_row[index])))
        commands.extend([('Подробности', lambda: self.notice('Подробности', self.rows[index][0].get() + '\n\n' + self.translate(self.rows[index][1].get()) + '\n' + self.row_details[index].cget('text'))), (None, None), ('Убрать из списка', lambda: self.remove_download_row(index))])
        if self.row_files.get(index):
            commands.append(('Удалить файл', lambda: self.confirm_delete_files([index])))
        self.popup_commands(commands, event.x_root if event else None, event.y_root if event else None)

    def open_row_folder(self, index):
        paths = self.row_files.get(index)
        folder = Path(paths[0]).parent if paths else Path(self.jobs_by_row.get(index, {}).get('folder', self.folder.get()))
        reveal_folder(folder)

    def copy_text(self, text):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    def add_links_dialog(self):
        dialog = ctk.CTkToplevel(self.root)
        dialog.title(self.translate('Добавить несколько ссылок'))
        dialog.geometry('600x360')
        dialog.transient(self.root)
        self.label(dialog, 'Одна ссылка на строку', size=16).pack(anchor='w', padx=20, pady=16)
        box = ctk.CTkTextbox(dialog, height=200)
        box.pack(fill='both', expand=True, padx=20)
        def add():
            links = [line.strip() for line in box.get('1.0', 'end').splitlines() if line.strip()]
            for link in links:
                service = 'Instagram' if is_instagram_url(link) else 'YouTube' if any(host in (urlparse(link).hostname or '') for host in ('youtube.com', 'youtu.be')) else 'GetCourse'
                self.tabs.set(service)
                self.activate_tab()
                self.url.set(link)
                self.start(auto_start=False, prefer_queue=False)
            self.launch_next()
            dialog.destroy()
        self.button(dialog, 'Добавить', add).pack(anchor='e', padx=20, pady=16)
        self.localize_ui()

    def show_help(self):
        text = platform_text('Вставьте ссылку — загрузка начнётся автоматически или попадёт в очередь. Формат, качество и папка применяются к новым задачам. Пауза и отмена находятся в строке видео. Меню строки открывается правой кнопкой мыши или кнопкой … .\n\nEnter — добавить введённую ссылку\n⌘+N — добавить несколько ссылок\n⌘+, — настройки\nF1 — справка\n\nОчистка списка сохраняет файлы. Удаление файлов требует подтверждения.')
        if self.language == 'en':
            text = platform_text('Paste a link to download or queue it. Format, quality and folder apply to new tasks. Pause and cancel are on each active row. Right-click or use … for row actions.\n\nEnter — add entered link\n⌘+N — add multiple links\n⌘+, — settings\nF1 — help\n\nClearing the list keeps files. Deleting files requires confirmation.')
        self.notice(self.translate('Как пользоваться'), text)

    def show_errors(self):
        self.notice(self.translate('Журнал ошибок'), '\n\n'.join(self.error_log[-20:]) or self.translate('Ошибок нет'))

    def show_about(self):
        dialog = ctk.CTkToplevel(self.root)
        dialog.title(self.translate('О ClipFlow'))
        dialog.geometry('560x400')
        dialog.transient(self.root)
        self.label(dialog, 'ClipFlow', size=28, weight='bold').pack(anchor='w', padx=24, pady=(24, 4))
        self.label(dialog, self.translate('Версия ') + APP_VERSION, size=12, color=COLORS['muted']).pack(anchor='w', padx=24)
        self.label(dialog, self.translate('Видео и аудио — в вашей коллекции.'), size=16).pack(anchor='w', padx=24, pady=16)
        description = 'Загрузчик для YouTube, GetCourse и Instagram с очередью, выбором качества и сохранением сессий входа.' if self.language == 'ru' else 'YouTube, GetCourse and Instagram downloader with a queue, quality selection and saved sign-in sessions.'
        self.label(dialog, description, wraplength=490, justify='left').pack(anchor='w', padx=24)
        self.button(dialog, 'История изменений', lambda: self.notice(self.translate('История изменений'), '1.7.0 — Compact interface, menus, queue filters, batch links, row progress and account controls.\n1.6.1 — Row pause/cancel, paste-to-download.\n1.6.0 — Embedded YouTube sign-in.')).pack(anchor='w', padx=24, pady=(20, 8))
        self.button(dialog, 'Скопировать информацию для поддержки', lambda: self.copy_text(f'ClipFlow {APP_VERSION}\nWindows\nLanguage: {self.language}\nyt-dlp: {yt_dlp.version.__version__}'), kind='outline', width=360).pack(anchor='w', padx=24)
        self.button(dialog, 'Лицензии компонентов', lambda: self.notice(self.translate('Лицензии компонентов'), 'yt-dlp — Unlicense\nCustomTkinter — MIT\nPython — PSF License\nQt / PySide6 — LGPLv3\nFFmpeg — LGPL/GPL (see bundled build)\nNode.js — MIT\nInstaloader — MIT\nPillow — HPND')).pack(anchor='w', padx=24, pady=8)
        self.localize_ui()

    def show_settings(self):
        dialog = ctk.CTkToplevel(self.root)
        dialog.title(self.translate('Настройки'))
        dialog.geometry('500x420')
        dialog.transient(self.root)
        self.label(dialog, 'Настройки', size=22, weight='bold').pack(anchor='w', padx=24, pady=20)
        self.label(dialog, 'Язык интерфейса').pack(anchor='w', padx=24)
        language = tk.StringVar(value='English' if self.language == 'en' else 'Русский')
        def change(value):
            self.language = 'en' if value == 'English' else 'ru'
            self.save_settings()
            self.localize_ui()
        self.option(dialog, language, ['Русский', 'English'], command=change, width=210).pack(anchor='w', padx=24, pady=(8, 16))
        self.label(dialog, 'Масштаб интерфейса').pack(anchor='w', padx=24)
        scale = tk.StringVar(value=self.interface_scale)
        def scale_changed(value):
            self.interface_scale = value
            ctk.set_widget_scaling(int(value[:-1]) / 100)
            self.save_settings()
        self.option(dialog, scale, ['90%', '100%', '110%', '125%'], command=scale_changed, width=210).pack(anchor='w', padx=24, pady=8)
        self.label(dialog, 'Скачивание', size=18, weight='bold').pack(anchor='w', padx=24, pady=(16, 8))
        self.button(dialog, 'Папка для скачивания', self.choose_folder, kind='outline', width=220).pack(anchor='w', padx=24)
        self.button(dialog, 'О ClipFlow', self.show_about, kind='outline').pack(anchor='w', padx=24, pady=16)
        self.localize_ui()

    def close(self):
        if self.busy:
            self.notice('Идёт скачивание', 'Сначала дождитесь завершения или нажмите «Отменить».')
            return
        self.root.destroy()


if __name__ == '__main__':
    if '--ui-self-test' in sys.argv:
        from self_test import run
        raise SystemExit(run(App, ctk))
    App(ctk.CTk()).root.mainloop()
