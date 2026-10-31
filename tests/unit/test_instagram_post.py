import copy
from dataclasses import replace

import pytest

from clipflow.domain.events import FilesSaved, RequestsDiscovered, WorkCancelled
from clipflow.providers.base import MediaFailure
from clipflow.providers.instagram_post import InstagramExtractor, InstagramPostProvider
from clipflow.providers.media import MediaPipeline
from tests.instagram_fixtures import context, isolate_instagram, photo, product, request, video


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    isolate_instagram(monkeypatch)


def fixture(monkeypatch, data):
    def extract(self, url):
        return self._extract_product(
            copy.deepcopy(data), video_id=self._match_id(url), get_comments=False
        )

    monkeypatch.setattr(InstagramExtractor, '_real_extract', extract)


def test_single_post_does_not_discover_profile(tmp_path, monkeypatch):
    data = product()
    data.pop('carousel_media')
    data.update(photo())
    fixture(monkeypatch, data)
    ctx, events, gate = context()
    result = InstagramPostProvider(MediaPipeline()).probe(request(tmp_path), ctx)
    assert len(result.items) == 1
    assert result.items[0].kind == 'photo'
    assert not any(isinstance(e, RequestsDiscovered) for e in events)
    assert gate.calls == []  # Synthetic extractor performs no HTTP request.


def test_carousel_img_index_does_not_truncate(tmp_path, monkeypatch):
    fixture(monkeypatch, product())
    ctx, _, _ = context()
    req = request(tmp_path, 'https://instagram.com/p/ABC/?img_index=2')
    result = InstagramPostProvider(MediaPipeline()).probe(req, ctx)
    assert [i.index for i in result.items] == [1, 2, 3]
    assert [i.kind for i in result.items] == ['photo', 'video', 'photo']
    assert all(i.info['post_code'] == 'ABC' for i in result.items)
    assert result.available_heights == (64,)


def test_profile_is_rejected_before_extracting(tmp_path, monkeypatch):
    def unexpected(*a, **kw):
        pytest.fail('Profile was fetched by post provider')

    monkeypatch.setattr(InstagramExtractor, '_real_extract', unexpected)
    ctx, _, _ = context()
    with pytest.raises(MediaFailure, match='instagram_post_required'):
        InstagramPostProvider(MediaPipeline()).probe(
            request(tmp_path, 'https://instagram.com/alice/'), ctx
        )


def test_missing_shared_policy_fails_closed_before_network(tmp_path, monkeypatch):
    def unexpected(*a, **kw):
        pytest.fail('Ungated Instagram request')

    monkeypatch.setattr(InstagramExtractor, '_real_extract', unexpected)
    ctx, _, _ = context()
    with pytest.raises(MediaFailure, match='instagram_rate_policy_required'):
        InstagramPostProvider(MediaPipeline()).probe(
            request(tmp_path), replace(ctx, instagram_rate=None)
        )


@pytest.mark.parametrize(
    ('media_filter', 'indices'), [('all', [1, 2, 3]), ('photo', [1, 3]), ('video', [2])]
)
def test_filter_keeps_original_indices(tmp_path, monkeypatch, media_filter, indices):
    fixture(monkeypatch, product())
    ctx, _, _ = context()
    result = InstagramPostProvider(MediaPipeline()).probe(
        request(tmp_path, media_filter=media_filter), ctx
    )
    assert [i.index for i in result.items] == indices


def test_video_thumbnail_is_not_a_photograph():
    item = photo()
    item['media_type'] = 2
    info = InstagramExtractor()._extract_product_media(item)
    assert not info.get('_clipflow_photo')


def test_highest_resolution_photo_and_original_extension():
    info = InstagramExtractor()._extract_product_media(photo())
    assert info['_clipflow_photo'] is True
    assert info['url'] == 'https://cdn.example.test/image.png'
    assert info['ext'] == 'png'
    assert (info['width'], info['height']) == (1000, 1000)


def test_unknown_author_is_not_invented_from_display_name(tmp_path, monkeypatch):
    data = product()
    data['user'] = {'pk': '123', 'full_name': 'Someone / Name'}
    fixture(monkeypatch, data)
    ctx, _, _ = context()
    result = InstagramPostProvider(MediaPipeline()).probe(request(tmp_path), ctx)
    assert all(i.info['author'] == 'Unknown author' for i in result.items)


def test_filter_with_no_matches_is_not_empty_success(tmp_path, monkeypatch):
    data = product()
    data['carousel_media'] = [video()]
    fixture(monkeypatch, data)
    ctx, events, _ = context()
    with pytest.raises(MediaFailure, match='instagram_no_matching_media'):
        InstagramPostProvider(MediaPipeline()).execute(request(tmp_path, media_filter='photo'), ctx)
    assert not any(isinstance(e, FilesSaved) for e in events)


@pytest.mark.parametrize(
    ('status', 'code'),
    [
        (429, 'instagram_rate_limited'),
        (403, 'instagram_access_denied'),
        (401, 'instagram_access_denied'),
    ],
)
def test_metadata_http_failures_are_specific_and_safe(tmp_path, monkeypatch, capsys, status, code):
    from io import BytesIO

    from yt_dlp.networking.common import Response
    from yt_dlp.networking.exceptions import HTTPError

    def fail(*a, **kw):
        raise HTTPError(
            Response(
                BytesIO(b''),
                url='https://instagram.com/?signed=synthetic-secret',
                headers={},
                status=status,
            )
        )

    monkeypatch.setattr(InstagramExtractor, '_real_extract', fail)
    ctx, _, gate = context()
    with pytest.raises(MediaFailure, match=code) as error:
        InstagramPostProvider(MediaPipeline()).probe(request(tmp_path), ctx)
    output = capsys.readouterr()
    assert 'synthetic-secret' not in str(error.value) + output.out + output.err
    assert gate.calls == []  # Error injected above transport; actual HTTP tested separately.


def test_cancelled_probe_never_fetches_post(tmp_path, monkeypatch):
    def unexpected(*a, **kw):
        pytest.fail('Cancelled post used network')

    monkeypatch.setattr(InstagramExtractor, '_real_extract', unexpected)
    ctx, _, gate = context()
    ctx.cancel.cancel('pause')
    with pytest.raises(WorkCancelled):
        InstagramPostProvider(MediaPipeline()).probe(request(tmp_path), ctx)
    assert gate.calls == []


def test_selection_and_invalid_snapshot_do_not_guess(tmp_path, monkeypatch):
    fixture(monkeypatch, product())
    ctx, _, _ = context()
    provider = InstagramPostProvider(MediaPipeline())
    req = request(tmp_path)
    all_items = provider.probe(req, ctx).items
    result = provider.probe(replace(req, selection=(all_items[2].id,)), ctx)
    assert [i.index for i in result.items] == [3]
    with pytest.raises(MediaFailure, match='instagram_selection_changed'):
        provider.probe(replace(req, selection=('missing-id',)), ctx)


@pytest.mark.parametrize(
    'info',
    [
        None,
        {'_type': 'playlist', 'entries': [None]},
        {'_type': 'url', 'url': 'https://instagram.com/alice/'},
        {'id': 'private', 'formats': []},
    ],
)
def test_incomplete_metadata_never_claims_success(tmp_path, monkeypatch, info):
    monkeypatch.setattr(InstagramExtractor, '_real_extract', lambda *a: info)
    ctx, events, _ = context()
    with pytest.raises(MediaFailure):
        InstagramPostProvider(MediaPipeline()).execute(request(tmp_path), ctx)
    assert not any(isinstance(e, (FilesSaved, RequestsDiscovered)) for e in events)
