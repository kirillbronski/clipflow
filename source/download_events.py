"""Collapse a burst of download telemetry without crossing lifecycle events."""


def coalesce_updates(events):
    result, telemetry = [], {}

    def flush():
        # Render the newest ETA before the progress text that includes it.
        for kind in ('eta', 'progress'):
            result.extend(event for event in telemetry.values() if event[0] == kind)
        telemetry.clear()

    for event in events:
        kind, value = event[:2]
        if kind in ('eta', 'progress'):
            run = event[2] if len(event) == 3 else None
            telemetry[(run, kind, value[0])] = event
        else:
            flush()
            result.append(event)
    flush()
    return result
