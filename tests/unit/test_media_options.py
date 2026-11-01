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


def test_main_download_never_asks_for_subtitles():
    # Subtitles come from a separate best-effort pass: a failed fetch cannot fail the video.
    assert 'writesubtitles' not in options(subtitles='ru')
    assert {'key': 'FFmpegEmbedSubtitle'} not in options(subtitles='ru')['postprocessors']


def test_rate_limit_downloads_fragments_one_at_a_time():
    assert options()['concurrent_fragment_downloads'] == 8
    assert options(rate_limit=1024 * 1024)['concurrent_fragment_downloads'] == 1


def test_subtitle_languages():
    from clipflow.providers.media import subtitle_languages

    assert subtitle_languages('ru', {}) == ['ru(-.*)?']
    assert subtitle_languages('en', {}) == ['en(-.*)?']
    original = {
        'formats': [
            {'acodec': 'opus', 'vcodec': 'none', 'language': 'de', 'language_preference': 10},
            {'acodec': 'opus', 'vcodec': 'none', 'language': 'en', 'language_preference': -1},
        ]
    }
    assert subtitle_languages('original', original) == ['de(-.*)?']
    assert subtitle_languages('original', {'automatic_captions': {'fr-orig': [], 'en': []}}) == [
        'fr(-.*)?'
    ]
    assert subtitle_languages('original', {}) is None  # yt-dlp then picks one track itself
    assert subtitle_languages(None, original) == []


def test_subtitle_fetch_failure_is_silent(tmp_path):
    from clipflow.providers.media import MediaPipeline

    def broken(*args, **kwargs):
        raise RuntimeError('HTTP 429')

    pipeline = MediaPipeline()
    request = DownloadRequest(parse_url('https://youtu.be/abc'), DownloadOptions(tmp_path))
    item = MediaItem('abc', 1, 'video', 'Ролик', {})
    context = ExecutionContext(
        CancellationToken(),
        lambda event: None,
        Auth(),
        preferences=DownloadPreferences(subtitles='ru'),
    )
    assert pipeline._fetch_subtitles(item, request, context, tmp_path / 'x.mp4', broken) == ()
