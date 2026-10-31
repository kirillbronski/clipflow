"""Versioned preferences beside legacy files, with atomic writes and safe migration."""

import json
import os
import shutil
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import NamedTemporaryFile
from types import MappingProxyType
from uuid import uuid4

from clipflow.domain.models import DownloadOptions, Service
from clipflow.infrastructure.repository import storage_code
from clipflow.infrastructure.serialization import decode_options, encode_options, path_value


class SettingsError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _presets():
    return {service: DownloadOptions(Path.home() / 'Downloads' / 'ClipFlow') for service in Service}


@dataclass(frozen=True)
class AppSettings:
    schema_version: int = 2
    theme: str = 'dark'
    language: str = 'ru'
    auto_start: bool = False
    presets: Mapping[Service, DownloadOptions] = field(default_factory=_presets)
    recent_folders: tuple[Path, ...] = ()
    profile_limit: int | None = 10

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version != 2:
            raise ValueError('invalid_schema')
        if self.theme not in {'dark', 'light', 'system'} or self.language not in {'ru', 'en'}:
            raise ValueError('invalid_preferences')
        if type(self.auto_start) is not bool:
            raise ValueError('invalid_auto_start')
        if self.profile_limit is not None and (
            type(self.profile_limit) is not int or self.profile_limit not in (10, 50)
        ):
            raise ValueError('invalid_profile_limit')
        if set(self.presets) != set(Service):
            raise ValueError('invalid_presets')
        presets = {Service(key): value for key, value in self.presets.items()}
        for value in presets.values():
            encode_options(value)
        object.__setattr__(self, 'presets', MappingProxyType(presets))
        recent = tuple(
            dict.fromkeys(path_value(str(p)).expanduser().resolve() for p in self.recent_folders)
        )[:10]
        object.__setattr__(self, 'recent_folders', recent)


class SettingsStore:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.path = self.directory / 'settings-v2.json'
        self.last_warning = None

    def _write(self, path, data):
        temporary = None
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(
                mode='w', encoding='utf-8', dir=self.directory, suffix='.tmp', delete=False
            ) as output:
                temporary = Path(output.name)
                json.dump(data, output, ensure_ascii=False, allow_nan=False, indent=2)
                output.write('\n')
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
            if os.name == 'posix':
                descriptor = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
        except OSError as error:
            raise SettingsError(storage_code(error)) from None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def save(self, settings: AppSettings):
        # Revalidate the snapshot; credential values are never auth references.
        settings = AppSettings(
            settings.schema_version,
            settings.theme,
            settings.language,
            settings.auto_start,
            settings.presets,
            settings.recent_folders,
            settings.profile_limit,
        )
        self._write(
            self.path,
            {
                'schema_version': 2,
                'theme': settings.theme,
                'language': settings.language,
                'auto_start': settings.auto_start,
                'profile_limit': settings.profile_limit,
                'recent_folders': [str(p) for p in settings.recent_folders],
                'presets': {
                    key.value: encode_options(value) for key, value in settings.presets.items()
                },
            },
        )

    def _decode(self, raw):
        if not isinstance(raw, dict):
            raise ValueError('invalid_settings')
        version = raw.get('schema_version')
        if 'schema_version' in raw and (type(version) is not int or version != 2):
            raise SettingsError('unsupported_settings_schema')
        if type(version) is not int:
            raise ValueError('invalid_schema')
        if not isinstance(raw['recent_folders'], list):
            raise ValueError('invalid_recent_folders')
        return AppSettings(
            version,
            raw['theme'],
            raw['language'],
            raw['auto_start'],
            {Service(key): decode_options(value) for key, value in raw['presets'].items()},
            tuple(path_value(p) for p in raw['recent_folders']),
            raw['profile_limit'],
        )

    def load(self):
        self.last_warning = None
        try:
            text = self.path.read_text(encoding='utf-8-sig')
        except FileNotFoundError:
            return self._migrate()
        except UnicodeError:
            return self._reset()
        except OSError as error:
            raise SettingsError(storage_code(error)) from None
        try:
            return self._decode(json.loads(text))
        except (ValueError, TypeError, KeyError, AttributeError, UnicodeError):
            return self._reset()

    def _reset(self):
        backup = self.directory / f'settings-v2.{uuid4().hex}.bak'
        try:
            shutil.copy2(self.path, backup)
        except OSError as error:
            raise SettingsError(storage_code(error)) from None
        settings = AppSettings()
        self.save(settings)
        self.last_warning = 'settings_reset'
        return settings

    def _migrate(self):  # noqa: C901  # подпроект 3
        legacy = self.directory / 'settings.json'
        try:
            raw = json.loads(legacy.read_text(encoding='utf-8-sig'))
            if not isinstance(raw, dict):
                raw = {}
        except FileNotFoundError:
            settings = AppSettings()
            self.save(settings)
            return settings
        except (ValueError, UnicodeError):
            raw = {}
            self.last_warning = 'legacy_settings_reset'
        except OSError as error:
            raise SettingsError(storage_code(error)) from None
        defaults = AppSettings()
        presets = dict(defaults.presets)
        folder = raw.get('folder')
        try:
            folder = path_value(folder).expanduser().resolve()
        except (ValueError, OSError):
            folder = defaults.presets[Service.YOUTUBE].folder
        quality = raw.get('quality')
        height = None
        if isinstance(quality, str):
            import re

            match = re.fullmatch(r'(360|480|720|1080|1440|2160)p(?: \(4K\))?', quality)
            if match:
                height = int(match.group(1))
        for service in Service:
            presets[service] = DownloadOptions(folder, max_height=height)

        def flag(key, default):
            value = raw.get(key, default)
            return value if type(value) is bool else default

        from dataclasses import replace

        presets[Service.INSTAGRAM] = replace(
            presets[Service.INSTAGRAM],
            author_folder=flag('instagram_author_folder', True),
            post_folder=flag('instagram_post_folder', True),
            description=('md' if raw.get('instagram_description_format') == 'MD' else 'txt')
            if flag('save_instagram_description', False)
            else None,
        )
        recent = []
        for value in raw.get('folders', []) if isinstance(raw.get('folders'), list) else []:
            try:
                recent.append(path_value(value).expanduser().resolve())
            except (ValueError, OSError):
                continue
        raw_limit = raw.get('instagram_profile_limit')
        limit = (
            {'До 10 публикаций': 10, 'До 50 публикаций': 50, 'Все публикации': None}.get(
                raw_limit, 10
            )
            if isinstance(raw_limit, str)
            else 10
        )
        language = raw.get('language') if raw.get('language') in ('ru', 'en') else 'ru'
        settings = AppSettings(
            language=language, presets=presets, recent_folders=tuple(recent), profile_limit=limit
        )
        # The original stays byte-for-byte intact. Back up only normalized
        # whitelisted preferences, never unknown/nested credential-like fields.
        ig = settings.presets[Service.INSTAGRAM]
        backup = {
            'folder': str(folder),
            'folders': [str(p) for p in settings.recent_folders],
            'language': language,
            'quality': f'{height}p' if height else 'Лучшее доступное',
            'instagram_author_folder': ig.author_folder,
            'instagram_post_folder': ig.post_folder,
            'save_instagram_description': ig.description is not None,
            'instagram_description_format': (ig.description or 'txt').upper(),
            'instagram_profile_limit': f'До {limit} публикаций' if limit else 'Все публикации',
        }
        self._write(self.directory / f'settings-v1.{uuid4().hex}.bak', backup)
        self.save(settings)
        return settings
