"""Turn a job's error code and options into the short texts shown in its queue row."""

import re

from clipflow.application.groups import GroupSummary
from clipflow.domain.failures import AUTH_SETTINGS_CODES, failure_group
from clipflow.domain.models import Job, JobState, Service
from clipflow.ui.i18n import Translator

SOURCE_NAMES = {
    Service.YOUTUBE: 'YouTube',
    Service.INSTAGRAM: 'Instagram',
    Service.GETCOURSE: 'GetCourse',
}
SEPARATOR = '  ·  '
_ITEM = re.compile(r'instagram_item_failed:(\d{1,3}):([a-z_]+)')


def _reason(code: str | None, service: Service, translator: Translator) -> str:
    if not code:
        return translator.text('job_error.unknown')  # nothing to report: no code to ask for
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


def _plural(count: int) -> str:
    """Russian plural form for a count: one, few or many."""
    if count % 10 == 1 and count % 100 != 11:
        return 'one'
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return 'few'
    return 'many'


_ITEM_WORDS = {
    'video': {'one': 'group_video_one', 'few': 'group_video_few', 'many': 'group_video_many'},
    'post': {'one': 'group_post_one', 'few': 'group_post_few', 'many': 'group_post_many'},
}


def size_text(size: int, translator: Translator) -> str:
    """Bytes as KB, MB or GB with one decimal; Russian uses a decimal comma."""
    for unit, scale in (('gb', 1024**3), ('mb', 1024**2), ('kb', 1024)):
        if size >= scale or unit == 'kb':
            value = f'{size / scale:.1f}'
            if translator.language == 'ru':
                value = value.replace('.', ',')
            return value + ' ' + translator.text(unit)
    raise AssertionError('unreachable')


def count_text(summary: GroupSummary, translator: Translator) -> str:
    """«76 видео» / «12 постов» for a group's members."""
    total = summary.total
    english = 'one' if total == 1 else 'many'
    form = _plural(total) if translator.language == 'ru' else english
    service = summary.parent.request.link.service
    word = _ITEM_WORDS['post' if service == Service.INSTAGRAM else 'video'][form]
    return translator.text(word, count=total)


def group_details(summary: GroupSummary, translator: Translator) -> str:
    """The group screen's header: member count and the size downloaded so far."""
    parts = [count_text(summary, translator)]
    if summary.size_bytes:
        parts.append(size_text(summary.size_bytes, translator))
    return SEPARATOR.join(parts)


def group_text(
    summary: GroupSummary,
    translator: Translator,
    title: str | None = None,
    percent: int | None = None,
) -> str | None:
    """The second line of a playlist or profile row; None while its list is still awaited."""
    parent = summary.parent
    service = parent.request.link.service
    if summary.total == 0:
        if parent.state == JobState.FAILED:
            reason = error_text(parent.error, service, translator)
            return translator.text('group_list_failed') + SEPARATOR + reason
        return None
    if summary.current is not None:
        parts = [translator.text('group_progress', done=summary.completed, total=summary.total)]
        if title:
            parts.append(translator.text('group_now', title=title))
        if percent is not None:
            parts.append(f'{percent}%')
        return SEPARATOR.join(parts)
    parts = [
        count_text(summary, translator),
        translator.text('group_downloaded', count=summary.completed),
    ]
    if summary.failed:
        parts.append(translator.text('group_failed', count=summary.failed))
    if summary.size_bytes:
        parts.append(size_text(summary.size_bytes, translator))
    return SEPARATOR.join(parts)
