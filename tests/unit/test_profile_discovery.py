from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from clipflow.domain.events import RequestsDiscovered, WorkCancelled
from clipflow.providers.base import MediaFailure
from clipflow.providers.instagram_profile import InstagramProfileProvider, PostRef, ProfilePage
from tests.instagram_fixtures import context, request


class Source:
    def __init__(self, pages):
        self.values = pages
        self.calls = 0

    def pages(self, request, context):
        self.calls += 1
        for page in self.values:
            if isinstance(page, Exception):
                raise page
            yield page


def post(i):
    return PostRef(f'C{i}', datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=i), 'alice')


def req(path, limit=None):
    return replace(request(path, 'https://instagram.com/alice/'), profile_limit=limit)


def codes(events):
    return [
        r.link.canonical_id for e in events if isinstance(e, RequestsDiscovered) for r in e.requests
    ]


def test_latest_10_with_old_pinned_posts(tmp_path):
    source = Source(
        [ProfilePage(tuple(map(post, [0, *range(20, 9, -1)])), None, False, frozenset({'C0'}))]
    )
    ctx, events, _ = context()
    provider = InstagramProfileProvider(source)
    provider.probe(req(tmp_path, 10), ctx)
    assert source.calls == 0
    result = provider.execute(req(tmp_path, 10), ctx)
    assert codes(events) == [f'C{i}' for i in range(20, 10, -1)] and result.discovered_count == 10
    assert source.calls == 1


def test_latest_50_merges_reels_without_duplicates(tmp_path):
    source = Source(
        [
            ProfilePage(tuple(post(i) for i in range(60)), 'reels', False, frozenset()),
            ProfilePage(tuple(post(i) for i in range(30, 80)), None, False, frozenset()),
        ]
    )
    ctx, events, _ = context()
    InstagramProfileProvider(source).execute(req(tmp_path, 50), ctx)
    assert codes(events) == [f'C{i}' for i in range(79, 29, -1)]
    assert all(len(e.requests) <= 25 for e in events if isinstance(e, RequestsDiscovered))


def test_all_paginates_until_exhausted(tmp_path):
    source = Source(
        [
            ProfilePage((post(0), post(1)), 'more', False, frozenset()),
            ProfilePage((post(1), post(2)), None, False, frozenset()),
        ]
    )
    ctx, events, _ = context()
    assert InstagramProfileProvider(source).execute(req(tmp_path), ctx).discovered_count == 3
    assert codes(events) == ['C0', 'C1', 'C2']


def test_unknown_order_does_not_claim_latest_n(tmp_path):
    source = Source(
        [ProfilePage(tuple(post(i) for i in range(20)), 'not-exhausted', False, frozenset())]
    )
    ctx, events, _ = context()
    with pytest.raises(MediaFailure, match='instagram_profile_incomplete'):
        InstagramProfileProvider(source).execute(req(tmp_path, 10), ctx)
    assert codes(events) == []


def test_private_profile_requires_access(tmp_path):
    ctx, events, _ = context()
    with pytest.raises(MediaFailure, match='instagram_access_required'):
        InstagramProfileProvider(Source([MediaFailure('instagram_access_required')])).execute(
            req(tmp_path), ctx
        )


def test_cancellation_interrupts_backoff(tmp_path):
    ctx, _, _ = context()
    ctx.cancel.cancel('cancel')
    with pytest.raises(WorkCancelled):
        InstagramProfileProvider(Source([])).execute(req(tmp_path), ctx)


def test_expired_checkpoint_reenumerates_and_never_reuses_old_completeness(tmp_path):
    from clipflow.domain.urls import request_key
    from tests.unit.test_instagram_rate_policy import policy

    gate, _, _ = policy(tmp_path)
    ctx, events, _ = context()
    ctx = replace(ctx, instagram_rate=gate)
    item = req(tmp_path, 10)
    key = request_key(item)
    gate.store.checkpoint(key, 'expired', ['Old'], True)
    source = Source([ProfilePage((post(1),), 'not-complete', False, frozenset())])
    with pytest.raises(MediaFailure, match='instagram_profile_incomplete'):
        InstagramProfileProvider(source).execute(item, ctx)
    assert gate.store.get_checkpoint(key) == ('not-complete', ('C1',), False)
    source.values = [ProfilePage((post(2), post(1)), None, False, frozenset())]
    assert InstagramProfileProvider(source).execute(item, ctx).discovered_count == 2
    assert codes(events) == ['C2', 'C1']


def test_children_are_labelled_with_caption_or_code(tmp_path):
    captioned = PostRef(
        'C1', datetime(2026, 1, 2, tzinfo=UTC), 'alice', 'Закат над морем\nвторая строка'
    )
    source = Source([ProfilePage((captioned, post(0)), None, False, frozenset())])
    ctx, events, _ = context()
    InstagramProfileProvider(source).execute(req(tmp_path), ctx)
    labels = {
        r.link.canonical_id: r.label
        for e in events
        if isinstance(e, RequestsDiscovered)
        for r in e.requests
    }
    assert labels == {'C1': 'Закат над морем', 'C0': 'C0'}
