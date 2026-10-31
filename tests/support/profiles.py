"""Instagram profile pages and posts for discovery tests."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from clipflow.domain.events import RequestsDiscovered
from clipflow.providers.instagram_profile import PostRef
from tests.instagram_fixtures import request


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


def codes(events):
    return [
        r.link.canonical_id for e in events if isinstance(e, RequestsDiscovered) for r in e.requests
    ]


def post(i):
    return PostRef(f'C{i}', datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=i), 'alice')


def req(path, limit=None):
    return replace(request(path, 'https://instagram.com/alice/'), profile_limit=limit)
