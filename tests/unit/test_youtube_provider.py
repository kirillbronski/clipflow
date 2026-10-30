"""Synthetic yt-dlp metadata at the network boundary, real provider contracts."""

import copy
from dataclasses import replace

import pytest
from yt_dlp import YoutubeDL

from clipflow.domain.events import (
    CancellationToken,
    FilesSaved,
    ProgressChanged,
    RequestsDiscovered,
    WorkCancelled,
)
from clipflow.domain.models import ContentKind, DownloadOptions, DownloadRequest, PlaylistPosition
from clipflow.domain.urls import parse_url, request_key
from clipflow.providers.base import ExecutionContext, MediaFailure
from clipflow.providers.media import MediaPipeline
from clipflow.providers.youtube import YouTubeProvider


class Auth:
    def options_for(self, profile, url):
        return {'http_headers': {'X-Test-Session': 'synthetic-secret'}}


def request(folder, url='https://youtu.be/video_A', **options):
    return DownloadRequest(parse_url(url), DownloadOptions(folder, **options))


def context():
    events = []
    return ExecutionContext(CancellationToken(), events.append, Auth()), events


def video(identity='video_A'):
    return {
        'id': identity,
        'title': 'Обычный ролик',
        '_type': 'video',
        'webpage_url': f'https://www.youtube.com/watch?v={identity}',
        'formats': [
            {
                'format_id': '720',
                'url': 'https://cdn.example.test/720.mp4',
                'ext': 'mp4',
                'height': 720,
                'vcodec': 'h264',
                'acodec': 'aac',
            },
            {
                'format_id': '1080',
                'url': 'https://cdn.example.test/1080.mp4',
                'ext': 'mp4',
                'height': 1080,
                'vcodec': 'h264',
                'acodec': 'aac',
            },
            {
                'format_id': 'a',
                'url': 'https://cdn.example.test/audio.m4a',
                'ext': 'm4a',
                'vcodec': 'none',
                'acodec': 'aac',
                'abr': 128,
            },
        ],
    }


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


def test_single_video(tmp_path, monkeypatch):
    extract_fixture(monkeypatch, video())
    ctx, _ = context()
    probe = YouTubeProvider(MediaPipeline()).probe(request(tmp_path), ctx)
    assert [(i.id, i.index, i.title) for i in probe.items] == [('video_A', 1, 'Обычный ролик')]
    assert probe.available_heights == (1080, 720)
    assert not probe.selection_required


def test_music_track_audio_mode(tmp_path, monkeypatch):
    info = video()
    info['formats'] = info['formats'][-1:]
    extract_fixture(monkeypatch, info)
    ctx, _ = context()
    req = request(tmp_path, 'https://music.youtube.com/watch?v=video_A', format='mp3')
    result = YouTubeProvider(MediaPipeline()).probe(req, ctx)
    assert result.items[0].id == 'video_A'
    assert result.available_heights == ()
    assert req.options.format == 'mp3'


def test_music_playlist(tmp_path, monkeypatch):
    extract_fixture(monkeypatch, playlist())
    ctx, events = context()
    req = request(tmp_path, 'https://music.youtube.com/playlist?list=PL_music', format='mp3')
    result = YouTubeProvider(MediaPipeline()).execute(req, ctx)
    children = [r for e in events if isinstance(e, RequestsDiscovered) for r in e.requests]
    assert result.files == () and result.discovered_count == 3
    assert [r.options.format for r in children] == ['mp3'] * 3
    assert [r.link.kind for r in children] == [ContentKind.VIDEO] * 3
    assert not any(isinstance(e, FilesSaved) for e in events)


def test_playlist_order_and_unavailable_entry(tmp_path, monkeypatch):
    extract_fixture(monkeypatch, playlist())
    ctx, events = context()
    req = request(tmp_path, 'https://www.youtube.com/playlist?list=PL_music')
    provider = YouTubeProvider(MediaPipeline())
    provider.execute(req, ctx)
    children = [r for e in events if isinstance(e, RequestsDiscovered) for r in e.requests]
    assert [r.link.canonical_id for r in children] == ['video_A', 'private_B', 'video_C']
    assert [r.playlist for r in children] == [
        PlaylistPosition('PL_music', 1, 'Музыка'),
        PlaylistPosition('PL_music', 3, 'Музыка'),
        PlaylistPosition('PL_music', 4, 'Музыка'),
    ]
    assert all(r.options == req.options for r in children)
    extract_fixture(monkeypatch, None)
    with pytest.raises(MediaFailure, match='unavailable_media'):
        provider.execute(children[1], ctx)
    extract_fixture(monkeypatch, video('video_C'))
    assert provider.probe(children[2], ctx).items[0].index == 4


def test_auth_options_are_not_in_result_or_logs(tmp_path, monkeypatch, capsys):
    info = video()
    info['http_headers'] = {'X-Test-Session': 'synthetic-secret'}
    extract_fixture(monkeypatch, info)
    ctx, events = context()
    result = YouTubeProvider(MediaPipeline()).probe(request(tmp_path, auth_profile='youtube'), ctx)
    assert 'synthetic-secret' not in repr(result) + repr(events)

    def failure(*args, **kwargs):
        raise RuntimeError('https://example.test/?password=synthetic-secret')

    monkeypatch.setattr(YoutubeDL, 'extract_info', failure)
    with pytest.raises(MediaFailure, match='probe_failed') as error:
        YouTubeProvider(MediaPipeline()).probe(request(tmp_path), ctx)
    assert 'synthetic-secret' not in str(error.value) + repr(error.value)
    output = capsys.readouterr()
    assert 'synthetic-secret' not in output.out + output.err


def test_audio_quality_not_misrepresented_as_lossless(tmp_path, monkeypatch):
    info = video()
    info['formats'] = info['formats'][-1:]
    extract_fixture(monkeypatch, info)
    ctx, _ = context()
    result = YouTubeProvider(MediaPipeline()).probe(request(tmp_path, format='mp3'), ctx)
    source = result.items[0].info['formats'][0]
    assert (source['acodec'], source['abr']) == ('aac', 128)
    assert 'lossless' not in repr(result).lower()


def test_empty_playlist_is_failure_not_empty_success(tmp_path, monkeypatch):
    extract_fixture(monkeypatch, {'_type': 'playlist', 'id': 'PL_empty', 'entries': [None]})
    ctx, events = context()
    with pytest.raises(MediaFailure, match='unavailable_media'):
        YouTubeProvider(MediaPipeline()).execute(
            request(tmp_path, 'https://youtube.com/playlist?list=PL_empty'), ctx
        )
    assert not any(isinstance(e, (RequestsDiscovered, FilesSaved)) for e in events)


def test_pre_cancelled_probe_never_accesses_network(tmp_path, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail('Cancelled probe used the network')

    monkeypatch.setattr(YoutubeDL, 'extract_info', unexpected)
    ctx, _ = context()
    ctx.cancel.cancel('pause')
    with pytest.raises(WorkCancelled):
        YouTubeProvider(MediaPipeline()).probe(request(tmp_path), ctx)


def test_playlist_position_is_identity_and_is_validated(tmp_path):
    req = request(tmp_path)
    first = replace(req, playlist=PlaylistPosition('PL_music', 1))
    other = replace(req, playlist=PlaylistPosition('PL_other', 1))
    second = replace(req, playlist=PlaylistPosition('PL_music', 2))
    assert len({request_key(req), request_key(first), request_key(other), request_key(second)}) == 4
    for identity, index in [('', 1), ('../bad', 1), ('PL_ok', 0), ('PL_ok', True), ('PL_ok', -2)]:
        with pytest.raises(ValueError):
            PlaylistPosition(identity, index)


def test_progress_burst_is_throttled_and_never_completes_job(monkeypatch):
    from clipflow.providers import media

    ctx, events = context()
    clock = [0.0]
    monkeypatch.setattr(media.time, 'monotonic', lambda: clock[0])
    hook = MediaPipeline._telemetry(ctx)
    for n in range(3000):
        clock[0] = n / 1000
        hook({'status': 'downloading', 'downloaded_bytes': n + 1, 'total_bytes_estimate': n + 1})
    clock[0] = 3
    hook({'status': 'finished', 'downloaded_bytes': 3000, 'total_bytes': 3000})
    assert len(events) <= 7
    assert all(isinstance(e, ProgressChanged) for e in events)
    assert events[-1].downloaded_bytes == 3000


def test_playlist_late_metadata_error_cannot_leak_auth(tmp_path, monkeypatch, capsys):
    def entries():
        yield playlist()['entries'][0]
        raise RuntimeError('signed-url?password=synthetic-secret')

    monkeypatch.setattr(
        YoutubeDL, 'extract_info', lambda *a, **k: {'_type': 'playlist', 'entries': entries()}
    )
    ctx, events = context()
    with pytest.raises(MediaFailure, match='probe_failed'):
        YouTubeProvider(MediaPipeline()).execute(
            request(tmp_path, 'https://youtube.com/playlist?list=PL_music'), ctx
        )
    assert not any(isinstance(e, RequestsDiscovered) for e in events)
    output = capsys.readouterr()
    assert 'synthetic-secret' not in output.out + output.err


def test_playlist_folders_do_not_share_another_playlists_finished_file(tmp_path):
    from clipflow.domain.paths import output_path
    from clipflow.providers.base import MediaItem

    req = request(tmp_path)
    item = MediaItem('video_A', 1, 'video', 'Одинаковое название', {})
    a = output_path(replace(req, playlist=PlaylistPosition('PL_music', 1)), item, None, None)
    b = output_path(replace(req, playlist=PlaylistPosition('PL_other', 1)), item, None, None)
    assert str(a).casefold() != str(b).casefold()


@pytest.mark.parametrize('raw', [None, [], 'bad metadata', {}])
def test_unavailable_or_malformed_metadata_is_safe(tmp_path, monkeypatch, raw):
    extract_fixture(monkeypatch, raw)
    ctx, _ = context()
    with pytest.raises(MediaFailure, match='unavailable_media'):
        YouTubeProvider(MediaPipeline()).probe(request(tmp_path), ctx)


def test_discovery_batches_are_bounded_and_cancellable(tmp_path, monkeypatch):
    info = {'_type': 'playlist', 'entries': [{'id': f'video_{i}'} for i in range(60)]}
    extract_fixture(monkeypatch, info)
    ctx, events = context()
    provider = YouTubeProvider(MediaPipeline())
    req = request(tmp_path, 'https://youtube.com/playlist?list=PL_many')
    assert provider.execute(req, ctx).discovered_count == 60
    assert [len(e.requests) for e in events if isinstance(e, RequestsDiscovered)] == [25, 25, 10]

    def stop_after_batch(event):
        if isinstance(event, RequestsDiscovered):
            ctx.cancel.cancel('cancel')

    with pytest.raises(WorkCancelled):
        provider.execute(req, replace(ctx, emit=stop_after_batch))


def test_selection_keeps_original_numbers(tmp_path, monkeypatch):
    extract_fixture(monkeypatch, playlist())
    ctx, events = context()
    req = replace(
        request(tmp_path, 'https://youtube.com/playlist?list=PL_music'), selection=('video_C',)
    )
    YouTubeProvider(MediaPipeline()).execute(req, ctx)
    children = [r for e in events if isinstance(e, RequestsDiscovered) for r in e.requests]
    assert len(children) == 1 and children[0].playlist.index == 4


def test_playlist_context_is_only_allowed_on_child_video(tmp_path):
    req = request(tmp_path, 'https://youtube.com/playlist?list=PL_music')
    with pytest.raises(ValueError):
        replace(req, playlist=PlaylistPosition('PL_music', 1))
    req = request(tmp_path, 'https://instagram.com/p/ABC/')
    with pytest.raises(ValueError):
        replace(req, playlist=PlaylistPosition('PL_music', 1))


def test_wrong_service_is_rejected_before_network(tmp_path, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail('Wrong service accessed YouTube extractor')

    monkeypatch.setattr(YoutubeDL, 'extract_info', unexpected)
    ctx, _ = context()
    with pytest.raises(MediaFailure, match='invalid_request'):
        YouTubeProvider(MediaPipeline()).probe(
            request(tmp_path, 'https://instagram.com/p/ABC/'), ctx
        )


def test_match_filter_checks_cancellation_without_wrapping_reason(tmp_path, monkeypatch):
    ctx, _ = context()

    def extract(self, url, download=False):
        assert self.params['match_filter']({'id': 'video_A'}, incomplete=True) is None
        ctx.cancel.cancel('pause')
        self.params['match_filter']({'id': 'video_A'}, incomplete=False)

    monkeypatch.setattr(YoutubeDL, 'extract_info', extract)
    with pytest.raises(WorkCancelled) as error:
        YouTubeProvider(MediaPipeline()).probe(request(tmp_path), ctx)
    assert error.value.reason == 'pause'


@pytest.mark.parametrize(
    'info',
    [
        dict(video(), _type='url'),
        dict(video(), id='../../bad'),
        {'id': 'video_A', 'title': 'Private video'},
    ],
)
def test_unresolved_or_unavailable_video_is_not_saved(tmp_path, monkeypatch, info):
    extract_fixture(monkeypatch, info)
    ctx, events = context()
    with pytest.raises(MediaFailure, match='unavailable_media'):
        YouTubeProvider(MediaPipeline()).execute(request(tmp_path), ctx)
    assert not any(isinstance(e, FilesSaved) for e in events)


def test_playlist_children_carry_entry_titles_and_parent_reports_playlist_title(
    tmp_path, monkeypatch
):
    from clipflow.domain.events import RequestsDiscovered, TitleChanged

    extract_fixture(monkeypatch, playlist())
    ctx, events = context()
    YouTubeProvider(MediaPipeline()).execute(
        DownloadRequest(
            parse_url('https://youtube.com/playlist?list=PL_music'), DownloadOptions(tmp_path)
        ),
        ctx,
    )
    children = [r for e in events if isinstance(e, RequestsDiscovered) for r in e.requests]
    assert [r.label for r in children] == ['Первый', '[Private video]', 'Последний']
    assert TitleChanged('Музыка') in events


def test_planned_title_is_the_future_file_name(tmp_path, monkeypatch):
    from dataclasses import replace
    from clipflow.domain.models import PlaylistPosition

    extract_fixture(
        monkeypatch, dict(video(), title='Мелом', artists=['Пропаганда'], track='Мелом')
    )
    ctx, _ = context()
    request = DownloadRequest(
        parse_url('https://music.youtube.com/watch?v=video_A'), DownloadOptions(tmp_path)
    )
    provider = YouTubeProvider(MediaPipeline())
    assert provider.planned_title(request, ctx) == 'Пропаганда - Мелом'
    numbered = replace(
        request,
        options=replace(request.options, numbering=True),
        playlist=PlaylistPosition('PL_music', 3, 'Sound City'),
    )
    assert provider.planned_title(numbered, ctx) == '003 - Пропаганда - Мелом'
