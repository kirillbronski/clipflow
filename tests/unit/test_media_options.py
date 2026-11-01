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


def test_rate_limit_is_not_a_ytdlp_option():
    # yt-dlp limits each download alone; the shared limiter keeps the total instead.
    assert 'ratelimit' not in options()
    assert 'ratelimit' not in options(rate_limit=2 * 1024 * 1024)


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


class Recorder:
    def __init__(self):
        self.counts = []

    def consume(self, count, cancel):
        self.counts.append(count)


def test_hook_reports_downloaded_bytes_to_limiter():
    recorder = Recorder()
    context = ExecutionContext(CancellationToken(), lambda event: None, Auth(), limiter=recorder)
    hook = MediaPipeline._telemetry(context)
    reports = (
        ('a', 100),  # first report is the baseline: it may include resumed bytes
        ('a', 250),
        ('a', 250),
        ('a', 400),
        ('b', 800 * 1024 * 1024),  # a resumed file: nothing downloaded yet in this run
        ('b', 800 * 1024 * 1024 + 50),
        ('a', 30),  # a retried fragment: the count goes down, then grows again
        ('a', 90),
        ('a', None),
    )
    for name, done in reports:
        hook({'status': 'downloading', 'filename': name, 'downloaded_bytes': done})
    assert recorder.counts == [150, 150, 50, 60]


def test_small_blocks_under_a_rate_limit():
    assert 'buffersize' not in options()
    limited = options(rate_limit=1024 * 1024)
    assert limited['buffersize'] == 65536
    assert limited['noresizebuffer'] is True


def test_subtitle_fetch_counts_against_the_shared_limit(tmp_path):
    recorder = Recorder()
    emitted = []
    request = DownloadRequest(parse_url('https://youtu.be/abc'), DownloadOptions(tmp_path))
    item = MediaItem('abc', 1, 'video', 'Ролик', {})
    context = ExecutionContext(
        CancellationToken(),
        emitted.append,
        Auth(),
        preferences=DownloadPreferences(subtitles='ru'),
        limiter=recorder,
    )

    class Downloader:
        def __init__(self, options, **kwargs):
            self.hooks = options['progress_hooks']

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def process_ie_result(self, info, download):
            for done in (10, 400, 900):
                for hook in self.hooks:
                    hook(
                        {'status': 'downloading', 'filename': 'x.ru.vtt', 'downloaded_bytes': done}
                    )

    MediaPipeline()._fetch_subtitles(item, request, context, tmp_path / 'x.mp4', Downloader)
    assert recorder.counts == [390, 500]
    assert emitted == []  # a subtitle file is not the video's progress
