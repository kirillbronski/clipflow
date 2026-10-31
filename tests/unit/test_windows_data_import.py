import pytest

from scripts.migrate_windows_data import migrate


def test_import_preserves_encrypted_bytes_and_existing_files(tmp_path):
    source = tmp_path / 'previous'
    target = tmp_path / 'new'
    source.mkdir()
    raw = b'opaque DPAPI profile\x00\xff'
    settings = b'{"language":"en"}'
    (source / 'settings.json').write_bytes(settings)
    (source / 'getcourse-profile.dat').write_bytes(raw)
    (source / 'unrelated.txt').write_text('keep')
    assert len(migrate(source, target)) == 2
    assert (
        (target / 'getcourse-profile.dat').read_bytes()
        == (source / 'getcourse-profile.dat').read_bytes()
        == raw
    )
    assert (target / 'settings.json').read_bytes() == settings
    assert not (target / 'unrelated.txt').exists()
    (target / 'settings.json').write_bytes(b'{"language":"ru"}')
    migrate(source, target)
    assert (target / 'settings.json').read_bytes() == b'{"language":"ru"}'
    for bad in (target, tmp_path / 'missing'):
        with pytest.raises(ValueError, match='Select a separate existing directory'):
            migrate(bad, target)
    (source / 'settings.json').write_text('invalid')
    with pytest.raises(ValueError, match='Expecting value'):
        migrate(source, tmp_path / 'invalid')
    assert not (tmp_path / 'invalid').exists()
