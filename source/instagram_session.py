"""Instagram session isolated from the user's YouTube profile."""
import time
from youtube_session import YouTubeSession

class InstagramSession(YouTubeSession):
    domain = 'instagram.com'
    login_flag = '--instagram-login'
    service = 'Instagram'

    @staticmethod
    def authenticated(cookies):
        return any(item.get('name') == 'sessionid' and item.get('value')
                   and (item.get('expires', -1) < 0 or item['expires'] > time.time())
                   for item in cookies)
