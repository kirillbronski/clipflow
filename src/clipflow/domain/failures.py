"""Kinds of job failure: every code a download can end with belongs to one group."""

_GROUPS = {
    'signin': (
        'auth_required',
        'auth_unavailable',
        'instagram_access_required',
        'instagram_access_denied',
        'getcourse_auth_failed',
        'getcourse_school_login_required',
    ),
    'access': (
        'unavailable_media',
        'instagram_unavailable_media',
        'getcourse_access_denied',
        'getcourse_no_media',
        'getcourse_invalid_player',
    ),
    'network': (
        'download_failed',
        'incomplete_download',
        'probe_failed',
        'getcourse_probe_failed',
        'instagram_probe_failed',
        'instagram_rate_limited',
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
FAILURE_GROUPS = {code: group for group, codes in _GROUPS.items() for code in codes}
# Sign-in settings failures have precise texts of their own instead of a group text.
AUTH_SETTINGS_CODES = frozenset(
    {
        'auth_invalid_settings',
        'auth_invalid_school',
        'auth_scope_mismatch',
        'auth_storage_failed',
        'auth_launch_failed',
    }
)


def failure_group(code: str | None) -> str:
    """Unknown or missing codes are internal failures."""
    return FAILURE_GROUPS.get(code, 'internal')
