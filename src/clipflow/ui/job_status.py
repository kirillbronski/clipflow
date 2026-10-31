"""Turn a job's error code and options into the short texts shown in its queue row."""

import re

from clipflow.domain.failures import AUTH_SETTINGS_CODES, failure_group
from clipflow.domain.models import Job, Service
from clipflow.ui.i18n import Translator

SOURCE_NAMES = {
    Service.YOUTUBE: 'YouTube',
    Service.INSTAGRAM: 'Instagram',
    Service.GETCOURSE: 'GetCourse',
}
SEPARATOR = '  ·  '
_ITEM = re.compile(r'instagram_item_failed:(\d{1,3}):([a-z_]+)')


def _reason(code: str | None, service: Service, translator: Translator) -> str:
    if code in AUTH_SETTINGS_CODES:
        return translator.text('error.' + code)
    return translator.text('job_error.' + failure_group(code), service=SOURCE_NAMES[service])


def error_text(code: str | None, service: Service, translator: Translator) -> str:
    item = _ITEM.fullmatch(code or '')
    if item is None:
        return _reason(code, service, translator)
    number, reason = item.groups()
    prefix = translator.text('job_error.item', number=int(number))
    return prefix + _reason(reason, service, translator)


def error_tooltip(code: str | None, service: Service, translator: Translator) -> str:
    text = error_text(code, service, translator)
    if not code:
        return text
    return text + '\n' + translator.text('job_error.code', code=code)


def meta_text(job: Job, translator: Translator) -> str:
    options = job.request.options
    service = job.request.link.service
    if service is Service.INSTAGRAM and options.media_filter == 'photo':
        parts = [translator.text('photo'), translator.text('original_format')]
    elif options.format == 'mp3':
        parts = ['MP3', translator.text('meta.mp3_quality')]
    elif service is Service.INSTAGRAM and options.media_filter == 'all':
        parts = [translator.text('meta.photos_videos'), options.format.upper()]
    elif options.max_height:
        parts = [options.format.upper(), translator.text('quality_cap', height=options.max_height)]
    else:
        parts = [options.format.upper(), translator.text('best_quality')]
    return SEPARATOR.join([SOURCE_NAMES[service], *parts])
