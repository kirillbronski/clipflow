"""Cover files beside the queue: atomic writes, removal with their jobs, safe names only."""

import pytest

from clipflow.infrastructure.thumbnails import ThumbnailStore


def test_save_is_atomic_and_readable(tmp_path):
    store = ThumbnailStore(tmp_path / 'thumbnails')
    assert not store.exists('job-1')
    store.save('job-1', b'jpeg')
    assert store.exists('job-1')
    assert store.path('job-1') == tmp_path / 'thumbnails' / 'job-1.jpg'
    assert store.path('job-1').read_bytes() == b'jpeg'
    assert [p.name for p in (tmp_path / 'thumbnails').iterdir()] == ['job-1.jpg']


def test_remove_and_prune(tmp_path):
    store = ThumbnailStore(tmp_path)
    for identity in ('a', 'b', 'c'):
        store.save(identity, b'x')
    (tmp_path / 'notes.txt').write_text('keep')
    store.remove(['a', 'missing'])
    assert not store.exists('a')
    store.prune({'c'})
    assert not store.exists('b')
    assert store.exists('c')
    assert (tmp_path / 'notes.txt').exists()


def test_prune_without_directory_is_quiet(tmp_path):
    ThumbnailStore(tmp_path / 'absent').prune(set())


@pytest.mark.parametrize('identity', ['../x', 'a/b', '', 'x' * 129, None])
def test_unsafe_id_is_rejected(tmp_path, identity):
    with pytest.raises(ValueError, match='invalid_job_identity'):
        ThumbnailStore(tmp_path).path(identity)
