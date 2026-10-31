"""YouTube extractor fixtures and execution contexts."""

import copy

from yt_dlp import YoutubeDL

from clipflow.domain.events import (
    CancellationToken,
)
from clipflow.providers.base import ExecutionContext


class Auth:
    def options_for(self, profile, url):
        return {'http_headers': {'X-Test-Session': 'synthetic-secret'}}


def context():
    events = []
    return ExecutionContext(CancellationToken(), events.append, Auth()), events


def extract_fixture(monkeypatch, info):
    def extract(self, url, download=False):
        assert download is False
        return copy.deepcopy(info)

    monkeypatch.setattr(YoutubeDL, 'extract_info', extract)


def playlist():
    return {
        '_type': 'playlist',
        'id': 'PL_music',
        'title': 'Музыка',
        'entries': [
            {
                '_type': 'url',
                'ie_key': 'Youtube',
                'id': 'video_A',
                'url': 'https://www.youtube.com/watch?v=video_A',
                'title': 'Первый',
                'playlist_index': 1,
            },
            None,
            {
                '_type': 'url',
                'ie_key': 'Youtube',
                'id': 'private_B',
                'url': 'https://www.youtube.com/watch?v=private_B',
                'title': '[Private video]',
                'availability': 'private',
                'playlist_index': 3,
            },
            {
                '_type': 'url',
                'ie_key': 'Youtube',
                'id': 'video_C',
                'url': 'https://www.youtube.com/watch?v=video_C',
                'title': 'Последний',
                'playlist_index': 4,
            },
        ],
    }
