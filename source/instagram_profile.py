"""Enumerate profile publications; media still uses ClipFlow's ordinary post worker."""
import re
from urllib.parse import urlparse
from yt_dlp.utils import DownloadError


def profile_username(url):
    parsed = urlparse(url)
    host = (parsed.hostname or '').lower()
    name = parsed.path.strip('/')
    reserved = {'p', 'reel', 'reels', 'tv', 'stories', 'explore', 'accounts', 'direct', 'about', 'developer', 'legal'}
    if (parsed.scheme in ('http', 'https') and not parsed.username and not parsed.password
            and (host == 'instagram.com' or host.endswith('.instagram.com'))
            and re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.]{0,29}', name)
            and name.lower() not in reserved):
        return name
    return None


def profile_posts(url, limit, cookies, cancel, progress=lambda count: None):
    import instaloader
    name = profile_username(url)
    if not name or limit not in (0, 10, 50, 100):
        raise DownloadError('Некорректная ссылка или лимит профиля Instagram.')

    class Controller(instaloader.RateController):
        def sleep(self, seconds):
            if cancel.wait(seconds):
                raise DownloadError('Скачивание отменено')

        def wait_before_query(self, query_type):
            if cancel.is_set():
                raise DownloadError('Скачивание отменено')
            super().wait_before_query(query_type)

        def handle_429(self, query_type):
            raise DownloadError('Instagram ограничил запросы. Повторите позже; готовые файлы сохранятся.')

    with instaloader.Instaloader(quiet=True, max_connection_attempts=1, request_timeout=20,
                                fatal_status_codes=[401, 403, 429], rate_controller=Controller) as loader:
        try:
            if cookies:
                loader.context.update_cookies(cookies)
                username = loader.test_login()
                if not username:
                    raise DownloadError('Сессия Instagram истекла. Войдите снова через меню «Аккаунты».')
                loader.load_session(username, loader.context.save_session())
            profile = instaloader.Profile.from_username(loader.context, name)
            if profile.is_private and not (profile.followed_by_viewer or profile.is_self):
                raise DownloadError('Закрытый профиль: нужен вход в аккаунт с доступом к публикациям.')
            posts = {}
            # Include Reels not shared to the main grid, and deduplicate shared posts.
            for method in (profile.get_posts, profile.get_reels):
                count = 0
                for post in method():
                    if cancel.is_set():
                        raise DownloadError('Скачивание отменено')
                    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', post.shortcode):
                        raise DownloadError('Instagram вернул некорректный код публикации.')
                    posts[post.shortcode] = post.date_utc
                    progress(len(posts))
                    count += 1
                    if limit and count >= limit:
                        break
            ordered = sorted(posts, key=lambda code: posts[code], reverse=True)
            if limit:
                ordered = ordered[:limit]
            return ['https://www.instagram.com/p/' + code + '/' for code in ordered]
        except DownloadError:
            raise
        except (instaloader.exceptions.InstaloaderException, instaloader.exceptions.AbortDownloadException) as error:
            raise DownloadError('Не удалось получить профиль Instagram. Возможно, нужен вход через меню «Аккаунты» или Instagram ограничил запросы. Повторите позже.') from error
