"""Protect existing ClipFlow data and opaque encrypted profiles during import."""
from pathlib import Path
import runpy
import tempfile

migrate = runpy.run_path('scripts/migrate_windows_data.py')['migrate']
with tempfile.TemporaryDirectory() as temp:
    source, target = Path(temp) / 'previous', Path(temp) / 'ClipFlow'
    source.mkdir()
    settings = b'{"language":"en"}'
    encrypted = b'opaque DPAPI profile\x00\xff'
    (source / 'settings.json').write_bytes(settings)
    (source / 'getcourse-profile.dat').write_bytes(encrypted)
    (source / 'unrelated.txt').write_text('leave untouched')
    result = migrate(source, target)
    assert len(result) == 2
    assert (target / 'settings.json').read_bytes() == settings
    assert (target / 'getcourse-profile.dat').read_bytes() == encrypted
    assert (source / 'getcourse-profile.dat').read_bytes() == encrypted
    assert not (target / 'unrelated.txt').exists()
    (target / 'settings.json').write_bytes(b'{"language":"ru"}')
    migrate(source, target)
    assert (target / 'settings.json').read_bytes() == b'{"language":"ru"}'
    for directory in (target, Path(temp) / 'missing'):
        try:
            migrate(directory, target)
        except ValueError:
            pass
        else:
            raise AssertionError('Unsafe source was accepted')
    (source / 'settings.json').write_text('invalid JSON')
    invalid_target = Path(temp) / 'invalid'
    try:
        migrate(source, invalid_target)
    except ValueError:
        pass
    else:
        raise AssertionError('Invalid settings were accepted')
    assert not invalid_target.exists()
print('PASS data import: original bytes preserved, existing files untouched, invalid sources rejected')
