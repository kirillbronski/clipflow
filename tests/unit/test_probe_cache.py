"""Recent link checks are reused for two minutes; at most a hundred are kept."""

from dataclasses import replace
from pathlib import Path

from clipflow.application.probe_cache import ProbeCache
from clipflow.domain.models import DownloadOptions, DownloadRequest
from clipflow.domain.urls import parse_url


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def request(url='https://youtu.be/ABC', **options):
    return DownloadRequest(parse_url(url), DownloadOptions(Path('/downloads'), **options))


def test_entry_is_fresh_until_the_ttl():
    clock = Clock()
    cache = ProbeCache(clock=clock)
    key = ProbeCache.key_for(request())
    cache.put(key, (1080, 720))
    clock.now += 119.9
    assert cache.get(key) == (1080, 720)
    clock.now += 0.1
    assert cache.get(key) is None


def test_the_oldest_entry_leaves_when_full():
    cache = ProbeCache(clock=Clock())
    keys = [ProbeCache.key_for(request(f'https://youtu.be/v{n}')) for n in range(101)]
    for key in keys:
        cache.put(key, (720,))
    assert cache.get(keys[0]) is None
    assert cache.get(keys[1]) == (720,)
    assert cache.get(keys[100]) == (720,)


def test_clear_forgets_everything():
    cache = ProbeCache(clock=Clock())
    key = ProbeCache.key_for(request())
    cache.put(key, (720,))
    cache.clear()
    assert cache.get(key) is None


def test_key_tells_profiles_and_audio_apart_but_not_containers():
    base = request()
    with_profile = replace(base, options=replace(base.options, auth_profile='p1'))
    assert ProbeCache.key_for(base) != ProbeCache.key_for(with_profile)
    assert ProbeCache.key_for(request(format='mp3')) != ProbeCache.key_for(request())
    assert ProbeCache.key_for(request(format='webm')) == ProbeCache.key_for(request())


def test_an_empty_quality_list_is_a_cached_answer():
    cache = ProbeCache(clock=Clock())
    key = ProbeCache.key_for(request())
    cache.put(key, ())
    assert cache.get(key) == ()
