"""Plain-language job error reasons and the metadata line of queue rows."""

import re
from pathlib import Path

import pytest

from clipflow.domain.models import DownloadOptions, DownloadRequest, Job, JobState, Service
from clipflow.domain.urls import parse_url
from clipflow.ui.i18n import Translator
from clipflow.ui.job_status import (
    AUTH_SETTINGS_CODES,
    ERROR_GROUPS,
    error_text,
    error_tooltip,
    meta_text,
)

SOURCE = Path(__file__).resolve().parents[2] / 'src' / 'clipflow'
NETWORK_RU = 'Не удалось скачать. Проверьте интернет и повторите.'
INTERNAL_RU = 'Внутренняя ошибка ClipFlow. Повторите; если не помогло — сообщите код.'


@pytest.fixture
def ru(qapp):
    return Translator('ru')


@pytest.fixture
def en(qapp):
    return Translator('en')


def source_error_codes():
    pattern = re.compile(r"(?:MediaFailure|WorkFailed)\(\s*'([a-z_]+)'")
    codes = {'no_output'}
    for path in SOURCE.rglob('*.py'):
        codes.update(pattern.findall(path.read_text(encoding='utf-8')))
    return codes


def test_every_source_error_code_has_specific_text():
    codes = source_error_codes()
    assert len(codes) > 20
    missing = sorted(
        code for code in codes if code not in ERROR_GROUPS.keys() | AUTH_SETTINGS_CODES
    )
    assert missing == []


def test_signin_names_the_service(ru):
    assert (
        error_text('auth_required', Service.INSTAGRAM, ru)
        == 'Нужен вход в Instagram. Откройте «Аккаунты».'
    )


@pytest.mark.parametrize(
    ('code', 'russian', 'english'),
    [
        (
            'getcourse_auth_failed',
            'Нужен вход в YouTube. Откройте «Аккаунты».',
            'Sign-in to YouTube is required. Open Accounts.',
        ),
        (
            'unavailable_media',
            'Материал недоступен: удалён, закрыт или нет доступа.',
            'Item unavailable: removed, private or no access.',
        ),
        ('download_failed', NETWORK_RU, 'Download failed. Check your connection and try again.'),
        (
            'write_failed',
            'Не удалось сохранить файл. Проверьте папку и свободное место.',
            'Could not save the file. Check the folder and free space.',
        ),
        (
            'processing_failed',
            'Файл получен, но не обработан. Повторите загрузку.',
            'File received but not processed. Download it again.',
        ),
        (
            'tool_missing',
            'Не найден FFmpeg. Переустановите ClipFlow.',
            'FFmpeg not found. Reinstall ClipFlow.',
        ),
        (
            'instagram_selection_changed',
            'Содержимое по ссылке изменилось. Добавьте её заново.',
            'The link content has changed. Add it again.',
        ),
        ('no_output', 'По ссылке нет подходящих материалов.', 'No matching items at this link.'),
        (
            'worker_failed',
            INTERNAL_RU,
            'Internal ClipFlow error. Try again; if it persists, report the code.',
        ),
    ],
)
def test_group_texts_ru_en(ru, en, code, russian, english):
    assert error_text(code, Service.YOUTUBE, ru) == russian
    assert error_text(code, Service.YOUTUBE, en) == english


def test_auth_settings_codes_reuse_error_texts(ru):
    assert error_text('auth_scope_mismatch', Service.GETCOURSE, ru) == ru.text(
        'error.auth_scope_mismatch'
    )


def test_carousel_item_prefix(ru, en):
    code = 'instagram_item_failed:003:download_failed'
    assert error_text(code, Service.INSTAGRAM, ru) == f'Элемент 3 не скачан: {NETWORK_RU}'
    assert error_text(code, Service.INSTAGRAM, en) == (
        'Item 3 failed: Download failed. Check your connection and try again.'
    )


@pytest.mark.parametrize(
    'code', [None, '', 'something_new', 'instagram_item_failed:abc:x', 'instagram_item_failed']
)
def test_unknown_missing_or_malformed_codes_fall_back_to_internal(ru, code):
    assert error_text(code, Service.INSTAGRAM, ru) == INTERNAL_RU


def test_tooltip_appends_code(ru, en):
    assert error_tooltip('tool_missing', Service.YOUTUBE, ru) == (
        'Не найден FFmpeg. Переустановите ClipFlow.\nКод: tool_missing'
    )
    assert error_tooltip('tool_missing', Service.YOUTUBE, en).endswith('\nCode: tool_missing')
    assert error_tooltip(None, Service.YOUTUBE, ru) == INTERNAL_RU


def job(url, **options):
    request = DownloadRequest(parse_url(url), DownloadOptions(Path.home(), **options))
    return Job('job', request, JobState.FAILED)


YOUTUBE = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'
INSTAGRAM = 'https://www.instagram.com/p/ABC/'


@pytest.mark.parametrize(
    ('url', 'options', 'russian', 'english'),
    [
        (
            YOUTUBE,
            {'format': 'mp3'},
            'YouTube  ·  MP3  ·  320 кбит/с',
            'YouTube  ·  MP3  ·  320 kbps',
        ),
        (
            YOUTUBE,
            {},
            'YouTube  ·  MP4  ·  Лучшее качество',
            'YouTube  ·  MP4  ·  Best quality',
        ),
        (
            YOUTUBE,
            {'max_height': 720},
            'YouTube  ·  MP4  ·  до 720p',
            'YouTube  ·  MP4  ·  up to 720p',
        ),
        (
            INSTAGRAM,
            {'media_filter': 'photo'},
            'Instagram  ·  Фото  ·  Исходный формат',
            'Instagram  ·  Photos  ·  Original format',
        ),
        (
            INSTAGRAM,
            {'media_filter': 'all'},
            'Instagram  ·  Фото и видео  ·  MP4',
            'Instagram  ·  Photos and videos  ·  MP4',
        ),
        (
            INSTAGRAM,
            {'media_filter': 'video'},
            'Instagram  ·  MP4  ·  Лучшее качество',
            'Instagram  ·  MP4  ·  Best quality',
        ),
    ],
)
def test_meta_text(ru, en, url, options, russian, english):
    assert meta_text(job(url, **options), ru) == russian
    assert meta_text(job(url, **options), en) == english
