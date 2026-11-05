"""Only Ubuntu's restricted child browser needs the namespace workaround."""

import pytest

from clipflow.infrastructure.auth_process.__main__ import sandbox_environment


@pytest.mark.parametrize(
    ('system', 'flag', 'disabled'),
    [
        ('linux', '1\n', True),
        ('linux', '0\n', False),
        ('linux', None, False),
        ('win32', '1\n', False),
        ('darwin', '1', False),
    ],
)
def test_sandbox_environment_only_changes_restricted_linux(tmp_path, system, flag, disabled):
    path = tmp_path / 'flag'
    if flag is not None:
        path.write_text(flag)
    original = {'PATH': '/bin'}
    result = sandbox_environment(original, system, path)
    assert (result.get('QTWEBENGINE_DISABLE_SANDBOX') == '1') is disabled
    assert original == {'PATH': '/bin'}
