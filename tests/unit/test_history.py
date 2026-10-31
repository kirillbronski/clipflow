"""History rules without Qt: which cleared jobs may go and which files may be deleted."""

from pathlib import Path

import pytest
from clipflow.application.history import (
    HistoryError,
    deletion_paths,
    removable_targets,
    result_status,
)

from clipflow.domain.models import DownloadOptions, DownloadRequest, Job, JobState
from clipflow.domain.urls import parse_url


def job(identity, parent=None, state=JobState.COMPLETED, folder=Path('/downloads'), files=()):
    request = DownloadRequest(parse_url('https://youtu.be/' + identity), DownloadOptions(folder))
    return Job(identity, request, state=state, parent_id=parent, result_files=files)


FAMILY = (job('g'), job('p', parent='g'), job('c', parent='p'))


def test_parent_of_a_kept_child_is_kept():
    assert removable_targets((job('p'), job('c', parent='p')), {'p'}) == set()


def test_grandparent_chain_is_kept_through_a_kept_child():
    assert removable_targets(FAMILY, {'g', 'p'}) == set()


def test_whole_family_is_removable():
    assert removable_targets(FAMILY, {'g', 'p', 'c'}) == {'g', 'p', 'c'}


def test_unrelated_targets_are_removable():
    assert removable_targets(FAMILY + (job('x'),), {'x'}) == {'x'}


def test_child_alone_is_removable():
    assert removable_targets(FAMILY, {'c'}) == {'c'}


def test_missing_result_file_is_reported(tmp_path):
    kept = tmp_path / 'a.mp4'
    kept.write_bytes(b'x')
    assert result_status(job('a', folder=tmp_path, files=(kept,))) == 'completed'
    gone = job('b', folder=tmp_path, files=(kept, tmp_path / 'gone.mp4'))
    assert result_status(gone) == 'files_missing'


def test_deletion_refuses_busy_jobs(tmp_path):
    with pytest.raises(HistoryError) as raised:
        deletion_paths((job('a', state=JobState.DOWNLOADING, folder=tmp_path),), ())
    assert raised.value.code == 'job_busy'


@pytest.mark.parametrize('name', ['../outside.mp4', 'sub'])
def test_deletion_refuses_paths_outside_or_folders(tmp_path, name):
    root = tmp_path / 'root'
    (root / 'sub').mkdir(parents=True)
    target = root / name
    with pytest.raises(HistoryError) as raised:
        deletion_paths((job('a', folder=root, files=(target,)),), ())
    assert raised.value.code == 'unsafe_result_path'


def test_deletion_refuses_files_an_active_job_still_writes(tmp_path):
    media = tmp_path / 'a.mp4'
    media.write_bytes(b'x')
    done = job('a', folder=tmp_path, files=(media,))
    active = job('b', state=JobState.DOWNLOADING, folder=tmp_path)
    with pytest.raises(HistoryError) as raised:
        deletion_paths((done,), (done, active))
    assert raised.value.code == 'job_busy'


def test_deletion_lists_each_recorded_file_once(tmp_path):
    media = tmp_path / 'a.mp4'
    media.write_bytes(b'x')
    first = job('a', folder=tmp_path, files=(media,))
    second = job('b', folder=tmp_path, files=(media,))
    assert deletion_paths((first, second), (first, second)) == (media,)
