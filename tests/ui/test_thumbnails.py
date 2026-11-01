"""Covers are fetched one at a time, shrunk to 160×90 and live only as long as their job."""

import threading

from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QColor, QImage

from clipflow.domain.models import DownloadOptions, DownloadRequest, Job, MediaDetails
from clipflow.domain.urls import parse_url
from clipflow.infrastructure.repository import SqliteJobRepository
from clipflow.infrastructure.thumbnails import ThumbnailStore
from clipflow.ui.presenter_thumbnails import ThumbnailLoader


def picture(width=640, height=480, color='#ff0000'):
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor(color))
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, 'PNG')
    return bytes(data)


def add(repo, tmp_path, identity, cover='https://i.ytimg.com/{}.jpg'):
    details = MediaDetails(thumbnail=cover.format(identity)) if cover else None
    request = DownloadRequest(parse_url(f'https://youtu.be/{identity}'), DownloadOptions(tmp_path))
    repo.add(Job(identity, request, details=details))


def window_with(make_window, tmp_path, fetch, *identities, cover='https://i.ytimg.com/{}.jpg'):
    repo = SqliteJobRepository(tmp_path / 'covers.sqlite3')
    for identity in identities:
        add(repo, tmp_path, identity, cover)
    store = ThumbnailStore(tmp_path / 'thumbnails')
    window, _ = make_window(repository=repo, thumbnails=store)
    loader = window.presenter.thumbnails
    loader.fetch = fetch
    return window, loader, store, repo


class Fetch:
    def __init__(self, data):
        self.data = data
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        if isinstance(self.data, Exception):
            raise self.data
        return self.data


def test_thumbnail_is_saved_as_160x90(make_window, qtbot, tmp_path):
    fetch = Fetch(picture())
    _, loader, store, _ = window_with(make_window, tmp_path, fetch, 'video_A')
    ready = []
    loader.thumbnail_ready.connect(ready.append)
    loader.refresh()
    qtbot.waitUntil(lambda: ready == ['video_A'], timeout=3000)
    image = QImage(str(store.path('video_A')))
    assert (image.width(), image.height()) == (160, 90)
    assert fetch.calls == ['https://i.ytimg.com/video_A.jpg']
    assert loader.pixmap('video_A').width() == 160


def test_oversized_or_not_image_are_skipped_once(make_window, qtbot, tmp_path):
    for data in (b'\0' * (2 * 1024 * 1024 + 1), b'not a picture', OSError('timeout')):
        fetch = Fetch(data)
        folder = tmp_path / type(data).__name__ / str(len(fetch.calls) + id(fetch))
        folder.mkdir(parents=True)
        _, loader, store, _ = window_with(make_window, folder, fetch, 'video_A')
        loader.refresh()
        qtbot.waitUntil(lambda f=fetch: len(f.calls) == 1, timeout=3000)
        qtbot.wait(100)
        loader.refresh()
        qtbot.wait(100)
        assert len(fetch.calls) == 1
        assert not store.exists('video_A')
        assert loader.pixmap('video_A') is None


def test_http_cover_is_never_fetched(make_window, qtbot, tmp_path):
    fetch = Fetch(picture())
    repo = SqliteJobRepository(tmp_path / 'http.sqlite3')
    add(repo, tmp_path, 'video_A')
    store = ThumbnailStore(tmp_path / 'thumbnails')
    window, _ = make_window(repository=repo, thumbnails=store)
    window.presenter.thumbnails.fetch = fetch
    window.presenter.thumbnails.queue_cover('video_A', 'http://i.ytimg.com/a.jpg')
    qtbot.wait(150)
    assert fetch.calls == []


def test_one_download_at_a_time(make_window, qtbot, tmp_path):
    gate = threading.Event()
    active = []
    overlap = []

    def fetch(url):
        active.append(url)
        overlap.append(len(active) > 1)
        gate.wait(2)
        active.remove(url)
        return picture()

    _, loader, store, _ = window_with(make_window, tmp_path, fetch, 'video_A', 'video_B')
    loader.refresh()
    qtbot.waitUntil(lambda: len(overlap) == 1, timeout=3000)
    qtbot.wait(100)
    assert len(overlap) == 1
    gate.set()
    qtbot.waitUntil(lambda: store.exists('video_A') and store.exists('video_B'), timeout=3000)
    assert not any(overlap)


def test_thumbnail_for_removed_job_is_not_kept(make_window, qtbot, tmp_path):
    gate = threading.Event()
    calls = []

    def fetch(url):
        calls.append(url)
        gate.wait(2)
        return picture()

    window, loader, store, repo = window_with(make_window, tmp_path, fetch, 'video_A')
    loader.refresh()
    qtbot.waitUntil(lambda: bool(calls), timeout=3000)
    repo.remove(('video_A',))
    window.presenter._reload_jobs()
    gate.set()
    qtbot.wait(300)
    assert not store.exists('video_A')


def test_startup_prunes_orphans_and_removal_deletes_cover(make_window, qtbot, tmp_path):
    store = ThumbnailStore(tmp_path / 'thumbnails')
    store.save('gone', picture())
    store.save('video_A', picture())
    repo = SqliteJobRepository(tmp_path / 'prune.sqlite3')
    add(repo, tmp_path, 'video_A')
    window, _ = make_window(repository=repo, thumbnails=store)
    window.presenter.thumbnails.fetch = Fetch(picture())
    qtbot.waitUntil(lambda: not store.exists('gone'), timeout=3000)
    assert store.exists('video_A')
    repo.remove(('video_A',))
    window.presenter._reload_jobs()
    qtbot.waitUntil(lambda: not store.exists('video_A'), timeout=3000)


def test_pixmap_is_cached_and_refreshed_when_ready(make_window, qtbot, tmp_path):
    fetch = Fetch(picture(color='#00ff00'))
    _, loader, _, _ = window_with(make_window, tmp_path, fetch, 'video_A')
    assert loader.pixmap('video_A') is None  # no file yet; remembered without disk reads
    loader.refresh()
    qtbot.waitUntil(lambda: loader.pixmap('video_A') is not None, timeout=3000)
    assert loader.pixmap('video_A') is loader.pixmap('video_A')


def test_presenter_without_store_has_no_loader(make_window):
    window, _ = make_window()
    assert window.presenter.thumbnails is None
    assert isinstance(ThumbnailLoader, type)


def test_ready_cover_reaches_the_row(make_window, qtbot, tmp_path):
    from clipflow.ui.queue_model import JobListModel

    fetch = Fetch(picture())
    window, loader, _, _ = window_with(make_window, tmp_path, fetch, 'video_A')
    model = window.presenter.model
    assert model.index(0).data(JobListModel.CoverRole) is None
    loader.refresh()
    qtbot.waitUntil(lambda: model.index(0).data(JobListModel.CoverRole) is not None, timeout=3000)


def test_instagram_cover_comes_from_the_event_in_this_session(make_window, qtbot, tmp_path):
    from clipflow.domain.events import DetailsFound, JobEvent

    repo = SqliteJobRepository(tmp_path / 'ig.sqlite3')
    post = DownloadRequest(parse_url('https://www.instagram.com/p/ABC/'), DownloadOptions(tmp_path))
    repo.add(Job('post', post))
    store = ThumbnailStore(tmp_path / 'thumbnails')
    window, _ = make_window(repository=repo, thumbnails=store)
    fetch = Fetch(picture())
    window.presenter.thumbnails.fetch = fetch
    signed = 'https://scontent.cdninstagram.com/a.jpg?oh=x'
    window.presenter._on_event(
        JobEvent('post', '', DetailsFound(MediaDetails(width=1080, thumbnail=signed)))
    )
    qtbot.waitUntil(lambda: store.exists('post'), timeout=3000)
    assert fetch.calls == [signed]
    assert repo.get('post').details is None or repo.get('post').details.thumbnail is None


def test_pending_covers_of_removed_jobs_are_dropped(make_window, qtbot, tmp_path):
    gate = threading.Event()
    calls = []

    def fetch(url):
        calls.append(url)
        gate.wait(2)
        return picture()

    window, loader, _, repo = window_with(
        make_window, tmp_path, fetch, 'video_A', 'video_B', 'video_C'
    )
    loader.refresh()
    qtbot.waitUntil(lambda: bool(calls), timeout=3000)
    repo.remove(tuple(i for i in ('video_A', 'video_B', 'video_C') if f'{i}.jpg' not in calls[0]))
    window.presenter._reload_jobs()
    qtbot.wait(50)
    gate.set()
    qtbot.wait(400)
    assert len(calls) == 1


def test_loader_reads_the_model_not_the_repository(make_window, qtbot, tmp_path, monkeypatch):
    fetch = Fetch(picture())
    _, loader, store, repo = window_with(make_window, tmp_path, fetch, 'video_A')
    reads = []
    original = repo.list
    monkeypatch.setattr(repo, 'list', lambda *a, **k: reads.append(1) or original(*a, **k))
    loader.refresh()
    qtbot.waitUntil(lambda: store.exists('video_A'), timeout=3000)
    qtbot.wait(50)
    assert reads == []
