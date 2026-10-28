from dataclasses import replace
import json
import os

import pytest

from clipflow.infrastructure.settings import AppSettings,SettingsStore,SettingsError
from clipflow.domain.models import DownloadOptions,Service


def test_first_run_defaults_and_roundtrip(tmp_path):
    store=SettingsStore(tmp_path); settings=store.load()
    assert settings.schema_version==2 and settings.theme=='dark' and settings.language=='ru'
    assert settings.auto_start is False and settings.profile_limit==10
    assert set(settings.presets)==set(Service)
    presets=dict(settings.presets); presets[Service.YOUTUBE]=DownloadOptions(tmp_path,format='mp3',max_height=None)
    chosen=replace(settings,theme='system',language='en',presets=presets,recent_folders=(tmp_path,),profile_limit=None)
    store.save(chosen)
    assert SettingsStore(tmp_path).load()==chosen
    with pytest.raises(TypeError): chosen.presets[Service.YOUTUBE]=settings.presets[Service.YOUTUBE]


def test_corrupt_settings_backup_and_defaults(tmp_path):
    path=tmp_path/'settings-v2.json'; path.write_bytes(b'{invalid json')
    restored=SettingsStore(tmp_path).load()
    assert restored==AppSettings()
    assert any(p.read_bytes()==b'{invalid json' for p in tmp_path.glob('settings-v2.*.bak'))
    assert SettingsStore(tmp_path).load()==restored


def test_unknown_schema_never_overwrites(tmp_path):
    path=tmp_path/'settings-v2.json'; original=b'{"schema_version":99,"future":true}';path.write_bytes(original)
    with pytest.raises(SettingsError,match='unsupported_settings_schema'): SettingsStore(tmp_path).load()
    assert path.read_bytes()==original


def test_legacy_settings_migrate_without_touching_sessions(tmp_path):
    legacy={'folder':str(tmp_path/'downloads'),'folders':[str(tmp_path/f'p{i}') for i in range(12)],
            'language':'en','auto_download':True,'quality':'720p','instagram_author_folder':False,
            'instagram_post_folder':False,'save_instagram_description':True,'instagram_description_format':'MD',
            'instagram_profile_limit':'До 50 публикаций','password':'SYNTHETIC_SECRET','unknown':'drop'}
    old=tmp_path/'settings.json'; old.write_text(json.dumps(legacy),encoding='utf-8'); before=old.read_bytes()
    protected=tmp_path/'getcourse-profile.bin'; protected.write_bytes(b'synthetic-protected-session')
    store=SettingsStore(tmp_path); migrated=store.load()
    assert migrated.language=='en' and not migrated.auto_start and migrated.profile_limit==50
    assert len(migrated.recent_folders)==10
    ig=migrated.presets[Service.INSTAGRAM]
    assert ig.max_height==720 and ig.folder==tmp_path/'downloads'
    assert not ig.author_folder and not ig.post_folder and ig.description=='md'
    assert old.read_bytes()==before and protected.read_bytes()==b'synthetic-protected-session'
    assert 'SYNTHETIC_SECRET' not in (tmp_path/'settings-v2.json').read_text(encoding='utf-8')
    assert list(tmp_path.glob('settings-v1.*.bak'))
    assert all(b'SYNTHETIC_SECRET' not in p.read_bytes() for p in tmp_path.glob('settings-v1.*.bak'))
    assert store.load()==migrated


def test_atomic_save_failure_keeps_previous_settings(tmp_path,monkeypatch):
    store=SettingsStore(tmp_path); first=AppSettings(); store.save(first)
    before=(tmp_path/'settings-v2.json').read_bytes()
    def fail(*args): raise PermissionError('synthetic failure')
    monkeypatch.setattr(os,'replace',fail)
    with pytest.raises(SettingsError,match='storage_read_only'): store.save(replace(first,language='en'))
    assert (tmp_path/'settings-v2.json').read_bytes()==before
    assert not list(tmp_path.glob('*.tmp'))


def test_invalid_settings_values_restore_defaults(tmp_path):
    store=SettingsStore(tmp_path); store.save(AppSettings())
    path=tmp_path/'settings-v2.json'; raw=json.loads(path.read_text(encoding='utf-8'));raw['auto_start']='yes'
    path.write_text(json.dumps(raw),encoding='utf-8')
    assert store.load()==AppSettings()


def test_credential_values_are_not_profile_references(tmp_path):
    settings=AppSettings(); presets=dict(settings.presets)
    presets[Service.GETCOURSE]=DownloadOptions(tmp_path,auth_profile='email@example.test:password')
    with pytest.raises((SettingsError,ValueError)):
        SettingsStore(tmp_path).save(replace(settings,presets=presets))
    assert not (tmp_path/'settings-v2.json').exists()


def test_non_utf8_settings_are_backed_up(tmp_path):
    original=b'\xff\xfe broken settings'
    (tmp_path/'settings-v2.json').write_bytes(original)
    assert SettingsStore(tmp_path).load()==AppSettings()
    assert any(p.read_bytes()==original for p in tmp_path.glob('settings-v2.*.bak'))


@pytest.mark.parametrize('version',['99',True,99.0])
def test_unrecognized_schema_type_is_preserved(tmp_path,version):
    path=tmp_path/'settings-v2.json'; path.write_text(json.dumps({'schema_version':version}),encoding='utf-8')
    before=path.read_bytes()
    with pytest.raises(SettingsError,match='unsupported_settings_schema'): SettingsStore(tmp_path).load()
    assert path.read_bytes()==before


def test_invalid_legacy_fields_are_ignored_without_touching_original(tmp_path):
    path=tmp_path/'settings.json'
    path.write_text(json.dumps({'instagram_profile_limit':[],'folders':[None,4,'good','good'],'folder':False,
                                'quality':{},'language':[],'instagram_author_folder':'no'}),encoding='utf-8')
    before=path.read_bytes(); settings=SettingsStore(tmp_path).load()
    assert settings.profile_limit==10 and settings.language=='ru'
    assert settings.presets[Service.INSTAGRAM].author_folder is True
    assert len(settings.recent_folders)==1 and path.read_bytes()==before


def test_legacy_backup_does_not_copy_unknown_nested_values(tmp_path):
    path=tmp_path/'settings.json'
    path.write_text(json.dumps({'quality':{'password':'NESTED_SECRET'},'folders':[{'cookie':'NESTED_SECRET'}],
                                'instagram_author_folder':{'token':'NESTED_SECRET'}}),encoding='utf-8')
    before=path.read_bytes(); SettingsStore(tmp_path).load()
    assert path.read_bytes()==before
    assert all(b'NESTED_SECRET' not in p.read_bytes() for p in tmp_path.glob('settings-v1.*.bak'))


def test_normalized_legacy_backup_can_restore_preferences(tmp_path):
    first=tmp_path/'first'; first.mkdir()
    (first/'settings.json').write_text(json.dumps({'folder':str(tmp_path/'downloads'),'language':'en',
        'instagram_profile_limit':'До 50 публикаций','quality':'1440p','save_instagram_description':True}),encoding='utf-8')
    expected=SettingsStore(first).load()
    second=tmp_path/'restored'; second.mkdir()
    (second/'settings.json').write_bytes(next(first.glob('settings-v1.*.bak')).read_bytes())
    assert SettingsStore(second).load()==expected
