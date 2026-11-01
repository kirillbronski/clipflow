"""What a queue row is, how search text compares and how titles order, without Qt."""

from pathlib import Path

from clipflow.application.queue_view import job_kind, natural_key, normalize
from clipflow.domain.models import DownloadOptions, DownloadRequest, Job, MediaDetails
from clipflow.domain.urls import parse_url


def job(url, fmt='mp4', media_filter='all', details=None):
    options = DownloadOptions(Path('/d'), format=fmt, media_filter=media_filter)
    return Job('j', DownloadRequest(parse_url(url), options), details=details)


def test_kinds():
    assert job_kind(job('https://youtu.be/a', fmt='mp3')) == 'audio'
    assert job_kind(job('https://music.youtube.com/watch?v=a')) == 'audio'  # forced to MP3
    photo = MediaDetails(photo=True, width=1)
    assert job_kind(job('https://www.instagram.com/p/A/', details=photo)) == 'photo'
    assert job_kind(job('https://www.instagram.com/p/A/', media_filter='photo')) == 'photo'
    assert job_kind(job('https://www.instagram.com/p/A/')) == 'video'
    assert job_kind(job('https://youtu.be/a')) == 'video'


def test_normalize():
    assert normalize('  ЁЛКА ') == 'елка'
    assert normalize('Straße') == 'strasse'
    assert normalize(None) == ''


def test_natural_key_orders_numbers():
    titles = ['Урок 10', 'урок 2', 'Урок 1', 'Ёж']
    assert sorted(titles, key=natural_key) == ['Ёж', 'Урок 1', 'урок 2', 'Урок 10']  # ё as е
    assert natural_key('a2') < natural_key('a10')
    assert natural_key(None) == natural_key('')
