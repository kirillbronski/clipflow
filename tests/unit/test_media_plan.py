"""Where a material will be written, decided before any network or disk access."""

from datetime import datetime
from pathlib import Path

from clipflow.domain.models import DownloadOptions, DownloadRequest, MediaItem
from clipflow.domain.paths import PostIdentity, media_identity, output_path
from clipflow.domain.urls import parse_url
from clipflow.providers.media_plan import MediaPlan, plan_media

ROOT = Path('/downloads')


def request(url):
    return DownloadRequest(parse_url(url), DownloadOptions(ROOT))


def test_youtube_names_carry_identity_in_the_temporary_name_and_tag():
    req = request('https://youtu.be/ABC')
    item = MediaItem('ABC', 1, 'video', 'Song', {'author': 'Artist', 'ext': 'mp4'})
    plan = plan_media(req, item)
    identity = media_identity(req, item)
    assert plan.target == output_path(req, item, 'Artist', None)
    assert plan.tag == 'clipflow:' + identity
    assert plan.work == plan.target.with_name(plan.target.stem + '.' + identity)
    assert plan.post is None
    assert isinstance(plan, MediaPlan)


def test_instagram_post_identity_comes_from_metadata():
    req = request('https://www.instagram.com/p/XYZ/')
    published = datetime(2026, 1, 2)
    item = MediaItem(
        '1',
        1,
        'photo',
        'T',
        {'post_code': 'ABC', 'post_title': 'T', 'published_at': published, 'ext': 'jpg'},
    )
    plan = plan_media(req, item)
    assert plan.post == PostIdentity('ABC', 'T', published)
    assert plan.tag is None
    assert plan.work == plan.target
    assert plan.target == output_path(req, item, None, plan.post)


def test_instagram_falls_back_to_the_link_and_ignores_text_dates():
    req = request('https://www.instagram.com/p/XYZ/')
    item = MediaItem('1', 1, 'photo', 'T', {'published_at': '2026', 'ext': 'jpg'})
    plan = plan_media(req, item)
    assert plan.post == PostIdentity(req.link.canonical_id, None, None)


def test_getcourse_has_neither_tag_nor_post():
    req = request('https://school.getcourse.ru/teach/control/lesson/view/id/123')
    item = MediaItem('v', 1, 'video', 'Lesson', {})
    plan = plan_media(req, item)
    assert plan.tag is None and plan.post is None and plan.work == plan.target
