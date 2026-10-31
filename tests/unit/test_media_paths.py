"""Output layouts must not escape the root, collide posts, or renumber media."""

import os
import subprocess
from datetime import datetime

import pytest

from clipflow.domain.models import DownloadOptions, DownloadRequest
from clipflow.domain.paths import PostIdentity, UnsafePath, output_path
from clipflow.domain.urls import parse_url
from clipflow.providers.base import MediaItem


def request(root, url='https://www.instagram.com/p/ABC/', **options):
    return DownloadRequest(parse_url(url), DownloadOptions(root, **options))


def photo(index=1, title='Фото'):
    return MediaItem(str(index), index, 'photo', title, {'ext': 'jpg'})


def test_untitled_posts_cannot_collide(tmp_path):
    req = request(tmp_path)
    a = output_path(req, photo(), 'alice', PostIdentity('ABC', None, None))
    b = output_path(req, photo(), 'alice', PostIdentity('XYZ', None, None))
    assert a == tmp_path / 'Instagram/alice/Пост - ABC/01.jpg'
    assert b == tmp_path / 'Instagram/alice/Пост - XYZ/01.jpg'


def test_post_folder_off_includes_post_id(tmp_path):
    req = request(tmp_path, author_folder=False, post_folder=False)
    assert (
        output_path(req, photo(3), None, PostIdentity('ABC', None, None))
        == tmp_path / 'Instagram/ABC - 03.jpg'
    )


def test_filtered_items_keep_original_number(tmp_path):
    req = request(tmp_path, media_filter='photo')
    assert (
        output_path(req, photo(7), 'alice', PostIdentity('ABC', 'Кадр', datetime(2026, 10, 28)))
        == tmp_path / 'Instagram/alice/2026-10-28 - Кадр - ABC/07.jpg'
    )


def test_windows_reserved_unicode_and_long_path(tmp_path):
    req = request(tmp_path, url='https://youtu.be/BaW_jenozKc')
    item = MediaItem('video', 1, 'video', 'CON. ' + '🌈е\u0301/очень—длинное:имя' * 40, {})
    path = output_path(req, item, None, None)
    assert path.is_relative_to(tmp_path / 'YouTube')
    assert len(str(path).encode('utf-16-le')) // 2 <= 240
    assert len(path.stem) <= 80
    assert '🌈е\u0301' in path.name
    assert not any(c in path.name for c in '<>:"/\\|?*')
    assert '—' not in path.name
    assert path.suffix == '.mp4'


@pytest.mark.parametrize('title', ['CON', 'con.txt', 'AUX', 'COM1', 'LPT9', 'NUL', 'COM¹', 'LPT²'])
def test_reserved_names_are_portable(tmp_path, title):
    req = request(tmp_path, url='https://youtu.be/BaW_jenozKc')
    assert output_path(req, MediaItem('v', 1, 'video', title, {}), None, None).stem.startswith('_')


def test_playlist_number_and_postprocessed_extension(tmp_path):
    req = request(
        tmp_path, url='https://youtube.com/playlist?list=PL_test', format='webm', numbering=True
    )
    path = output_path(
        req, MediaItem('v', 12, 'video', 'Название — ролика', {'ext': 'mp4'}), None, None
    )
    assert path.parent == tmp_path / 'YouTube'
    assert path.name == '012 - Название - ролика.webm'


def test_getcourse_complete_title(tmp_path):
    req = request(tmp_path, url='https://school.getcourse.ru/pl/teach/control/lesson/view?id=123')
    path = output_path(req, MediaItem('v', 1, 'video', 'Урок 1 — Основы звука', {}), None, None)
    assert path.is_relative_to(tmp_path / 'GetCourse')
    assert path.name.startswith('Урок 1 - Основы звука [')
    assert path.suffix == '.mp4'


@pytest.mark.parametrize('code', ['../bad', '', 'ABC/xyz', 'CON'])
def test_unsafe_post_identity_is_rejected_or_sanitized(tmp_path, code):
    if code == 'CON':
        assert output_path(
            request(tmp_path), photo(), 'CON', PostIdentity(code, None, None)
        ).is_relative_to(tmp_path / 'Instagram/_CON')
    else:
        with pytest.raises(UnsafePath):
            output_path(request(tmp_path), photo(), None, PostIdentity(code, None, None))


def test_deep_root_fails_instead_of_escaping_or_silently_truncating(tmp_path):
    req = request(tmp_path / ('long' * 60))
    with pytest.raises(UnsafePath):
        output_path(req, photo(), None, PostIdentity('ABC', None, None))


def test_symlink_cannot_redirect_outside_root(tmp_path):
    outside = tmp_path / 'outside'
    outside.mkdir()
    root = tmp_path / 'downloads'
    root.mkdir()
    try:
        (root / 'Instagram').symlink_to(outside, target_is_directory=True)
    except OSError:
        if os.name != 'nt':
            raise
        # Junctions exercise the same resolved containment without symlink privilege.
        subprocess.run(
            ['cmd', '/c', 'mklink', '/J', str(root / 'Instagram'), str(outside)],
            capture_output=True,
            check=True,
        )
    with pytest.raises(UnsafePath):
        output_path(request(root), photo(), None, PostIdentity('ABC', None, None))


@pytest.mark.parametrize(
    'media',
    [
        MediaItem('x', 0, 'photo', '', {'ext': 'jpg'}),
        MediaItem('x', 1, 'photo', '', {'ext': 'exe'}),
        MediaItem('x', 1, 'audio', '', {}),
    ],
)
def test_invalid_media_layout_is_rejected(tmp_path, media):
    with pytest.raises(UnsafePath):
        output_path(request(tmp_path), media, None, PostIdentity('ABC', None, None))


def test_instagram_requires_post_and_profile_forces_post_folder(tmp_path):
    with pytest.raises(UnsafePath):
        output_path(request(tmp_path), photo(), None, None)
    req = request(tmp_path, url='https://instagram.com/alice/', post_folder=False)
    assert output_path(req, photo(), None, PostIdentity('ABC', None, None)).name == '01.jpg'


def test_too_long_instagram_folder_is_not_truncated_into_another_post(tmp_path):
    with pytest.raises(UnsafePath):
        output_path(
            request(tmp_path / ('nested' * 20)),
            photo(),
            None,
            PostIdentity('ABC', 'Подпись' * 10, None),
        )


@pytest.mark.parametrize('post_folder', [True, False])
def test_post_codes_differing_only_in_case_cannot_collide(tmp_path, post_folder):
    req = request(tmp_path, post_folder=post_folder)
    paths = [
        output_path(req, photo(), None, PostIdentity(code, None, None))
        for code in ('ABC', 'abc', 'Abc')
    ]
    assert len({str(p).casefold() for p in paths}) == 3


# YouTube names carry no hash; their collisions are resolved by the pipeline (test_youtube_worker).
@pytest.mark.parametrize('url', ['https://school.getcourse.ru/pl/teach/control/lesson/view?id=123'])
def test_same_title_different_media_and_quality_cannot_reuse_output(tmp_path, url):
    from dataclasses import replace

    req = request(tmp_path, url=url)
    items = [
        MediaItem(identity, 1, 'video', 'Introduction', {})
        for identity in ('AAAAAAAAAAA', 'BBBBBBBBBBB', 'aaaaaaaaaaa')
    ]
    paths = [output_path(req, media, None, None) for media in items]
    assert len({str(p).casefold() for p in paths}) == 3
    assert output_path(req, items[0], None, None) == paths[0]
    low = replace(req, options=replace(req.options, max_height=360))
    assert output_path(low, items[0], None, None) != paths[0]
    # Title truncation must never discard the identity suffix.
    long_items = [replace(media, title='A' * 200) for media in items]
    assert len({str(output_path(req, media, None, None)).casefold() for media in long_items}) == 3


def test_tight_generic_path_budget_rejects_instead_of_clipping_identity(tmp_path):
    from pathlib import Path

    # Choose an absolute folder for a deterministic 18-unit filename budget.
    root = Path('/') / ('x' * 168)
    req = request(root, url='https://school.getcourse.ru/pl/teach/control/lesson/view?id=123')
    with pytest.raises(UnsafePath):
        output_path(req, MediaItem('v', 1, 'video', 'A' * 100, {}), None, None)
    # YouTube has no name suffix to protect: it clips, identity lives in the file tag.
    clipped = output_path(
        request(root, url='https://youtu.be/AAAAAAAAAAA'),
        MediaItem('v', 1, 'video', 'A' * 100, {}),
        None,
        None,
    )
    # Drive-qualified roots (Windows) shorten the budget: assert the invariant, not one OS's number.
    assert set(clipped.stem) == {'A'}
    assert 8 <= len(clipped.stem) < 100
    assert len(str(clipped).encode('utf-16-le')) // 2 <= 200
