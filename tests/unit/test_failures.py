"""The domain knows which kinds of failure exist; the interface only words them."""

from clipflow.domain.failures import AUTH_SETTINGS_CODES, FAILURE_GROUPS, failure_group


def test_codes_map_to_their_group():
    assert failure_group('instagram_rate_limited') == 'network'
    assert failure_group('auth_required') == 'signin'
    assert failure_group('getcourse_invalid_player') == 'access'


def test_unknown_and_missing_codes_are_internal():
    assert failure_group(None) == 'internal'
    assert failure_group('never_seen') == 'internal'


def test_groups_are_the_known_set():
    assert set(FAILURE_GROUPS.values()) == {
        'signin',
        'access',
        'network',
        'save',
        'processing',
        'tool',
        'changed',
        'empty',
        'internal',
    }
    assert 'auth_scope_mismatch' in AUTH_SETTINGS_CODES
    assert not AUTH_SETTINGS_CODES & FAILURE_GROUPS.keys()
