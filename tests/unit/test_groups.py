"""Playlist and profile groups without Qt: membership and the one-row summary."""

from pathlib import Path

from clipflow.application.groups import descendants, group_summary, is_group, top_level_id
from clipflow.domain.models import DownloadOptions, DownloadRequest, Job, JobState
from clipflow.domain.urls import parse_url

PLAYLIST = 'https://www.youtube.com/playlist?list=PLgroup'
PROFILE = 'https://www.instagram.com/someone/'


def job(identity, parent=None, state=JobState.QUEUED, url=None):
    link = parse_url(url or 'https://youtu.be/' + identity)
    request = DownloadRequest(link, DownloadOptions(Path('/downloads')))
    return Job(identity, request, state=state, parent_id=parent)


def ids(jobs):
    return tuple(j.id for j in jobs)


def test_playlist_without_children_is_a_group():
    assert is_group(job('p', url=PLAYLIST), False)
    assert is_group(job('i', url=PROFILE), False)
    assert not is_group(job('single'), False)
    assert is_group(job('single'), True)
    assert not is_group(job('child', parent='p'), True)


def test_descendants_follow_parent_chains():
    jobs = (
        job('p', url=PLAYLIST),
        job('c1', parent='p'),
        job('s'),
        job('c2', parent='p'),
        job('r', parent='c1'),
    )
    groups = descendants(jobs)
    assert ids(groups['p']) == ('c1', 'c2', 'r')
    assert groups['s'] == ()
    assert set(groups) == {'p', 's'}


def test_orphans_belong_to_no_group():
    jobs = (job('p', url=PLAYLIST), job('c', parent='p'), job('lost', parent='gone'))
    groups = descendants(jobs)
    assert ids(groups['p']) == ('c',)
    assert 'lost' not in {j.id for members in groups.values() for j in members}


def test_summary_counts_states_and_sizes():
    parent = job('p', url=PLAYLIST, state=JobState.COMPLETED)
    members = (
        job('a', 'p', JobState.COMPLETED),
        job('b', 'p', JobState.COMPLETED),
        job('c', 'p', JobState.COMPLETED),
        job('d', 'p', JobState.FAILED),
        job('e', 'p', JobState.CANCELLED),
        job('f', 'p', JobState.QUEUED),
        job('g', 'p', JobState.DOWNLOADING),
    )
    summary = group_summary(parent, members, {'a': 10, 'b': 20, 'd': 99})
    assert (summary.total, summary.completed, summary.failed, summary.active) == (7, 3, 2, 2)
    assert summary.size_bytes == 30
    assert summary.current.id == 'g'
    assert summary.parent is parent


def test_summary_of_an_empty_group():
    parent = job('p', url=PLAYLIST, state=JobState.PROBING)
    summary = group_summary(parent, (), {})
    assert summary.total == 0
    assert summary.current is None
    assert summary.parent is parent


def test_top_level_id_walks_to_the_root():
    jobs = {j.id: j for j in (job('p'), job('c', 'p'), job('r', 'c'), job('lost', 'gone'))}
    assert top_level_id('r', jobs) == 'p'
    assert top_level_id('p', jobs) == 'p'
    assert top_level_id('lost', jobs) is None


def test_a_parent_cycle_belongs_to_no_group():
    jobs = (job('a', 'b'), job('b', 'a'), job('p', url=PLAYLIST))
    assert descendants(jobs) == {'p': ()}
    assert top_level_id('a', {j.id: j for j in jobs}) is None
