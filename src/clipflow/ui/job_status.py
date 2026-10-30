"""Turn a job's error code and options into the short texts shown in its queue row."""

import re

from clipflow.domain.models import Job, Service
from clipflow.ui.i18n import Translator

SOURCE_NAMES = {
    Service.YOUTUBE: 'YouTube',
    Service.INSTAGRAM: 'Instagram',
    Service.GETCOURSE: 'GetCourse',
}
SEPARATOR = '  ·  '
_GROUPS = {
    'signin': (
        'auth_required',
        'auth_unavailable',
        'instagram_access_required',
        'getcourse_auth_failed',
    ),
    'access': (
        'unavailable_media',
        'instagram_unavailable_media',
        'getcourse_access_denied',
        'getcourse_no_media',
    ),
    'network': (
        'download_failed',
        'incomplete_download',
        'probe_failed',
        'getcourse_probe_failed',
        'instagram_profile_failed',
        'instagram_profile_incomplete',
    ),
    'save': ('write_failed', 'invalid_path'),
    'processing': ('processing_failed', 'invalid_media', 'missing_output'),
    'tool': ('tool_missing',),
    'changed': ('getcourse_selection_changed', 'instagram_selection_changed'),
    'empty': ('no_output', 'instagram_no_matching_media'),
    'internal': (
        'worker_failed',
        'worker_start_failed',
        'invalid_request',
        'invalid_provider_event',
        'instagram_rate_policy_required',
        'instagram_post_required',
        'instagram_profile_required',
        'instagram_incomplete_metadata',
        'instagram_invalid_metadata',
    ),
}
ERROR_GROUPS = {code: group for group, codes in _GROUPS.items() for code in codes}
# Sign-in settings failures already have precise texts under ``error.<code>``.
AUTH_SETTINGS_CODES = frozenset(
    {
        'auth_invalid_settings',
        'auth_invalid_school',
        'auth_scope_mismatch',
        'auth_storage_failed',
        'auth_launch_failed',
    }
)
_ITEM = re.compile(r'instagram_item_failed:(\d{1,3}):([a-z_]+)')


def _reason(code: str | None, service: Service, translator: Translator) -> str:
    if code in AUTH_SETTINGS_CODES:
        return translator.text('error.' + code)
    group = ERROR_GROUPS.get(code, 'internal')
    return translator.text('job_error.' + group, service=SOURCE_NAMES[service])


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
    if options.format == 'mp3':
        parts = ['MP3', translator.text('meta.mp3_quality')]
    elif service is Service.INSTAGRAM and options.media_filter == 'photo':
        parts = [translator.text('photo'), translator.text('original_format')]
    elif service is Service.INSTAGRAM and options.media_filter == 'all':
        parts = [translator.text('meta.photos_videos'), options.format.upper()]
    elif options.max_height:
        parts = [options.format.upper(), translator.text('quality_cap', height=options.max_height)]
    else:
        parts = [options.format.upper(), translator.text('best_quality')]
    return SEPARATOR.join([SOURCE_NAMES[service], *parts])
