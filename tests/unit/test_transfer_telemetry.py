from clipflow.domain.events import CancellationToken, ProgressChanged
from clipflow.providers.base import ExecutionContext
from clipflow.providers.media import MediaPipeline


def test_fragment_burst_measures_speed_and_estimated_100_cannot_bypass_throttle(monkeypatch):
    clock = [0.0]
    events = []
    monkeypatch.setattr('clipflow.providers.media.time.monotonic', lambda: clock[0])
    context = ExecutionContext(CancellationToken(), events.append, None, None)
    hook = MediaPipeline._telemetry(context)
    for number in range(3000):
        clock[0] += 0.001
        hook(
            {
                'status': 'downloading',
                'downloaded_bytes': 1000000 + number * 1000,
                'total_bytes_estimate': 1,
                'speed': 1000000000,
                'filename': 'video',
            }
        )
    hook({'status': 'finished'})
    assert 5 <= len(events) <= 8
    assert all(
        e.speed_bytes_per_second is None or 0 <= e.speed_bytes_per_second < 2 * 1024 * 1024
        for e in events
    )
    assert events[-1].downloaded_bytes == 3999000


def test_next_stream_does_not_inherit_previous_total(monkeypatch):
    clock = [0.0]
    events = []
    monkeypatch.setattr('clipflow.providers.media.time.monotonic', lambda: clock[0])
    hook = MediaPipeline._telemetry(
        ExecutionContext(CancellationToken(), events.append, None, None)
    )
    hook({'status': 'finished', 'downloaded_bytes': 5000, 'total_bytes': 5000, 'filename': 'video'})
    clock[0] = 1.0
    hook({'status': 'downloading', 'downloaded_bytes': 100, 'filename': 'audio'})
    assert events[-1].downloaded_bytes == 100
    assert events[-1].total_bytes is None
    assert events[-1].speed_bytes_per_second is None
