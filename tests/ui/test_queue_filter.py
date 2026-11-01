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


def sized(identity, size=None, duration=None, title=None, parent=None, url=None):
    details = MediaDetails(size_bytes=size, duration=duration) if size or duration else None
    item = job(identity, url=url, parent=parent, details=details)
    if title:
        item = Job(item.id, item.request, parent_id=parent, details=details, title=title)
    return item


def test_sort_by_each_key_both_ways(qapp):
    jobs = [
        sized('a', 300, 10, 'Урок 10'),
        sized('b', 100, 30, 'Урок 2'),
        sized('c', 200, 20, 'урок 1'),
    ]
    _, proxy = make(jobs)
    assert shown(proxy) == ['a', 'b', 'c']
    expected = {'title': ['c', 'b', 'a'], 'size': ['b', 'c', 'a'], 'duration': ['a', 'c', 'b']}
    for key, order in expected.items():
        proxy.sort_by(key)
        assert shown(proxy) == order, key
        proxy.sort_by(key, descending=True)
        assert shown(proxy) == order[::-1], key
    proxy.sort_by('added', descending=True)
    assert shown(proxy) == ['c', 'b', 'a']
    proxy.sort_by('added')
    assert shown(proxy) == ['a', 'b', 'c']
    with pytest.raises(ValueError, match='invalid_sort'):
        proxy.sort_by('rating')


def test_unknown_values_sort_last_both_ways(qapp):
    jobs = [sized('old'), sized('big', 500, 50), sized('small', 5, 5)]
    _, proxy = make(jobs)
    for key in ('size', 'duration'):
        proxy.sort_by(key)
        assert shown(proxy) == ['small', 'big', 'old']
        proxy.sort_by(key, descending=True)
        assert shown(proxy) == ['big', 'small', 'old']


def test_ties_keep_queue_order(qapp):
    _, proxy = make([sized('x', 7), sized('y', 7), sized('z', 7)])
    proxy.sort_by('size')
    assert shown(proxy) == ['x', 'y', 'z']
    proxy.sort_by('size', descending=True)
    assert shown(proxy) == ['x', 'y', 'z']


def test_group_sorts_by_its_totals(qapp):
    jobs = [
        sized('single', 250, 25),
        sized('list', url=PLAYLIST),
        sized('t1', 100, 10, parent='list'),
        sized('t2', 200, 20, parent='list'),
    ]
    _, proxy = make(jobs)
    proxy.sort_by('size')
    assert shown(proxy) == ['single', 'list']  # 250 < 300
    proxy.sort_by('duration', descending=True)
    assert shown(proxy) == ['list', 'single']  # 30 > 25


def test_new_jobs_respect_sort_and_search(qapp):
    model, proxy = make([sized('b', 20, title='Бета'), sized('c', 30, title='Гамма')])
    proxy.sort_by('size')
    proxy.show_query('а')
    model.set_jobs([*model.jobs, sized('a', 10, title='Альфа'), sized('z', 1, title='Зет')])
    assert shown(proxy) == ['a', 'b', 'c']
