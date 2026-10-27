"""Routing must not confuse a profile, a post, or a lookalike host."""
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from clipflow.domain.models import ContentKind, DownloadOptions, DownloadRequest, Service
from clipflow.domain.urls import InvalidLink, parse_url, request_key


@pytest.mark.parametrize(('url', 'service', 'kind', 'identity'), [
    ('https://music.youtube.com/watch?v=abc123', Service.YOUTUBE, ContentKind.VIDEO, 'abc123'),
    ('https://youtu.be/abc123?si=tracking', Service.YOUTUBE, ContentKind.VIDEO, 'abc123'),
    ('https://youtube.com/shorts/abc123', Service.YOUTUBE, ContentKind.VIDEO, 'abc123'),
    ('https://youtube.com/playlist?list=PL_123', Service.YOUTUBE, ContentKind.PLAYLIST, 'PL_123'),
    ('https://instagram.com/p/ABC_12/?img_index=2', Service.INSTAGRAM, ContentKind.POST, 'ABC_12'),
    ('https://www.instagram.com/reel/ABC_12/?igsh=tracking', Service.INSTAGRAM, ContentKind.POST, 'ABC_12'),
    ('https://instagram.com/author.name/', Service.INSTAGRAM, ContentKind.PROFILE, 'author.name'),
    ('https://school.getcourse.ru/pl/teach/control/lesson/view?id=123&utm_source=x', Service.GETCOURSE, ContentKind.LESSON, 'school.getcourse.ru/pl/teach/control/lesson/view?id=123'),
    ('https://player02.getcourse.ru/sign-player/?json=fixture', Service.GETCOURSE, ContentKind.PLAYER, 'player02.getcourse.ru/sign-player/?json=fixture'),
])
def test_routes_content_by_exact_host_and_path(url, service, kind, identity):
    parsed = parse_url(url)
    assert (parsed.service, parsed.kind, parsed.canonical_id) == (service, kind, identity)


@pytest.mark.parametrize('url', [
    '', 'javascript:alert(1)', 'file:///tmp/movie.mp4',
    'https://youtube.com.evil.test/watch?v=abc',
    'https://instagram.com.evil.test/p/abc/', 'https://getcourse.ru.evil.test/x',
    'https://user:pass@instagram.com/name/', 'https://user@youtube.com/watch?v=abc',
    'https://youtube.com/watch?v=', 'https://youtu.be/', 'https://youtube.com/playlist?list=',
    'https://youtube.com/anything', 'https://instagram.com/p/',
    'https://instagram.com/accounts/', 'https://instagram.com/stories/name/',
    'https://instagram.com/explore/', 'https://instagram.com/a/b/',
    'https://instagram.com/../author/', 'https://instagram.com:abc/p/123',
])
def test_invalid_or_lookalike_links_are_rejected(url):
    with pytest.raises(InvalidLink):
        parse_url(url)


def test_tracking_and_alternative_post_paths_do_not_duplicate(tmp_path):
    options = DownloadOptions(folder=tmp_path)
    first = DownloadRequest(parse_url(' https://www.instagram.com/p/ABC/?img_index=2 '), options)
    second = DownloadRequest(parse_url('https://instagram.com/reel/ABC/?igsh=xyz'), options)
    assert request_key(first) == request_key(second)
    assert first.link.canonical_url == 'https://www.instagram.com/p/ABC/'


@pytest.mark.parametrize('change', [
    {'format': 'mkv'}, {'folder': Path('/another-folder')}, {'max_height': 720},
    {'description': 'md'}, {'author_folder': False}, {'post_folder': False},
    {'media_filter': 'photo'}, {'auth_profile': 'another-protected-account'},
])
def test_different_download_options_are_distinct_requests(tmp_path, change):
    options = DownloadOptions(folder=tmp_path)
    link = parse_url('https://youtu.be/abc')
    assert request_key(DownloadRequest(link, options)) != request_key(DownloadRequest(link, replace(options, **change)))


def test_profile_limit_and_lesson_selection_are_part_of_identity(tmp_path):
    options = DownloadOptions(folder=tmp_path)
    link = parse_url('https://instagram.com/name/')
    assert request_key(DownloadRequest(link, options, profile_limit=10)) != request_key(DownloadRequest(link, options, profile_limit=50))
    assert request_key(DownloadRequest(link, options, selection=('a',))) != request_key(DownloadRequest(link, options, selection=('b',)))


def test_options_are_immutable_and_validate_values(tmp_path):
    options = DownloadOptions(folder=tmp_path)
    with pytest.raises(FrozenInstanceError):
        options.format = 'mkv'
    for change in ({'format': 'exe'}, {'media_filter': 'unknown'}, {'description': 'html'}, {'max_height': -1}):
        with pytest.raises(ValueError):
            replace(options, **change)


def test_core_import_does_not_load_qt():
    import subprocess
    import sys
    result = subprocess.run([sys.executable, '-c', "import clipflow.domain.models; import sys; assert 'PySide6' not in sys.modules"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
