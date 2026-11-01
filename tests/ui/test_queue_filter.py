"""Kind tabs, search and sorting over the queue model, without the window."""

from pathlib import Path

import pytest

from clipflow.domain.models import (
    DownloadOptions,
    DownloadRequest,
    Job,
    JobState,
    MediaDetails,
)
from clipflow.domain.urls import parse_url
from clipflow.ui.queue_model import JobListModel, QueueFilter

PLAYLIST = 'https://www.youtube.com/playlist?list=PLgroup'


def job(identity, url=None, fmt='mp4', state=JobState.QUEUED, parent=None, details=None, **kw):
    options = DownloadOptions(Path('/d'), format=fmt, **kw)
    request = DownloadRequest(parse_url(url or f'https://youtu.be/{identity}'), options)
    return Job(identity, request, state=state, parent_id=parent, details=details)


def mixed():
    return [
        job('video', details=MediaDetails(author='Ёлкин')),
        job('song', fmt='mp3', state=JobState.COMPLETED),
        job(
            'pic', url='https://www.instagram.com/p/PIC/', details=MediaDetails(photo=True, width=1)
        ),
        job('list', url=PLAYLIST),
        job('track', fmt='mp3', parent='list'),
        job('clip', parent='list'),
    ]


def shown(proxy):
    return [proxy.index(r, 0).data(JobListModel.JobIdRole) for r in range(proxy.rowCount())]


def make(jobs):
    model = JobListModel(jobs)
    return model, QueueFilter(model)


def test_kind_tabs_on_a_mixed_queue(qapp):
    _, proxy = make(mixed())
    assert shown(proxy) == ['video', 'song', 'pic', 'list']
    proxy.show_kind('video')
    assert shown(proxy) == ['video', 'list']
    proxy.show_kind('audio')
    assert shown(proxy) == ['song', 'list']
    proxy.show_kind('photo')
    assert shown(proxy) == ['pic']
    proxy.show_kind('playlists')
    assert shown(proxy) == ['list']
    with pytest.raises(ValueError, match='invalid_kind'):
        proxy.show_kind('channels')


def test_kind_inside_a_group(qapp):
    _, proxy = make(mixed())
    proxy.show_group('list')
    proxy.show_kind('audio')
    assert shown(proxy) == ['track']
    proxy.show_kind('playlists')
    assert shown(proxy) == ['track', 'clip']


def test_search_by_title_author_and_link(qapp):
    _, proxy = make(mixed())
    proxy.show_query('елкин')
    assert shown(proxy) == ['video']
    proxy.show_query('instagram.com/p/PIC')
    assert shown(proxy) == ['pic']
    proxy.show_query('')
    assert len(shown(proxy)) == 4


def test_search_ignores_case_and_yo(qapp):
    jobs = [
        job('a', details=MediaDetails(author='ёлка')),
        job('b', details=MediaDetails(author='Елка')),
    ]
    _, proxy = make(jobs)
    proxy.show_query('ЁЛКА')
    assert shown(proxy) == ['a', 'b']


def test_search_finds_a_group_by_its_track(qapp):
    jobs = mixed()
    jobs[4] = Job(
        'track', jobs[4].request, parent_id='list', details=MediaDetails(author='Особый автор')
    )
    _, proxy = make(jobs)
    proxy.show_query('особый')
    assert shown(proxy) == ['list']
    proxy.show_group('list')
    assert shown(proxy) == ['track']


def test_counts_follow_kind_and_search(qapp):
    _, proxy = make(mixed())
    proxy.show_kind('audio')
    assert (proxy.count('all'), proxy.count('completed'), proxy.count('active')) == (2, 1, 1)
    proxy.show_query('song')
    assert (proxy.count('all'), proxy.count('completed')) == (1, 1)
