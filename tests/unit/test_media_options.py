"""yt-dlp options follow the download preferences: speed limit and embedded subtitles."""

from pathlib import Path

from clipflow.domain.events import CancellationToken
from clipflow.domain.models import DownloadOptions, DownloadPreferences, DownloadRequest, MediaItem
from clipflow.domain.urls import parse_url
from clipflow.providers.base import ExecutionContext
from clipflow.providers.media import MediaPipeline


class Auth:
    def options_for(self, profile, url):
        return {}


def options(url='https://youtu.be/abc', fmt='mp4', info=None, **preferences):
    request = DownloadRequest(parse_url(url), DownloadOptions(Path('/d'), format=fmt))
    item = MediaItem('abc', 1, 'video', 'Ролик', {'language': 'de'} if info is None else info)
    context = ExecutionContext(
        CancellationToken(),
        lambda event: None,
        Auth(),
        preferences=DownloadPreferences(**preferences),
    )
    return MediaPipeline()._options(item, request, context, Path('/d/Ролик.mp4'))


def test_rate_limit_option():
    assert 'ratelimit' not in options()
    assert options(rate_limit=2 * 1024 * 1024)['ratelimit'] == 2 * 1024 * 1024


def test_subtitles_for_youtube_video_only():
    youtube = options(subtitles='ru')
    assert youtube['writesubtitles'] is True
    assert youtube['writeautomaticsub'] is False
    assert youtube['subtitleslangs'] == ['ru']
    assert {'key': 'FFmpegEmbedSubtitle'} in youtube['postprocessors']
    assert 'writesubtitles' not in options(fmt='mp3', subtitles='ru')
    assert 'writesubtitles' not in options(url='https://www.instagram.com/p/ABC/', subtitles='ru')
    assert 'writesubtitles' not in options()


def test_original_language_from_info():
    assert options(subtitles='original')['subtitleslangs'] == ['de']
    fallback = options(subtitles='original', info={})
    assert fallback['subtitleslangs'] == ['all', '-live_chat']
