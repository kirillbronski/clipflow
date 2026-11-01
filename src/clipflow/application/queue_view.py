"""How the queue is shown: a row's kind, search text and the natural order of titles."""

import re

from clipflow.domain.models import Job, Service


def job_kind(job: Job) -> str:
    """'audio' for MP3, 'photo' for Instagram stills, otherwise 'video'."""
    options = job.request.options
    if options.format == 'mp3':
        return 'audio'
    photo = job.details is not None and job.details.photo
    if photo or (job.request.link.service is Service.INSTAGRAM and options.media_filter == 'photo'):
        return 'photo'
    return 'video'


def normalize(text: str | None) -> str:
    """Case, «ё» and edge spaces do not matter to search or sorting."""
    return (text or '').strip().casefold().replace('ё', 'е')


def natural_key(text: str | None) -> tuple:
    """«Урок 2» before «Урок 10»: digit runs compare as numbers."""
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part)
        for part in re.split(r'(\d+)', normalize(text))
        if part
    )


def plural(count: int, language: str) -> str:
    """'one', 'few' or 'many' for Russian; English has only 'one' and 'many'."""
    if language != 'ru':
        return 'one' if count == 1 else 'many'
    if count % 10 == 1 and count % 100 != 11:
        return 'one'
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return 'few'
    return 'many'
