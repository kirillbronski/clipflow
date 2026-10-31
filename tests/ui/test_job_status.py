"""Plain-language job error reasons and the metadata line of queue rows."""

import re
from pathlib import Path

import pytest
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QStyleOptionViewItem

from clipflow.domain.failures import AUTH_SETTINGS_CODES, FAILURE_GROUPS
from clipflow.domain.models import DownloadOptions, DownloadRequest, Job, JobState, Service
from clipflow.domain.urls import parse_url
from clipflow.infrastructure.repository import SqliteJobRepository
from clipflow.ui.i18n import Translator
from clipflow.ui.job_status import error_text, error_tooltip, meta_text
from clipflow.ui.queue_model import JobListModel

SOURCE = Path(__file__).resolve().parents[2] / 'src' / 'clipflow'
NETWORK_RU = 'Не удалось скачать. Проверьте интернет и повторите.'
INTERNAL_RU = 'Внутренняя ошибка ClipFlow. Повторите; если не помогло — сообщите код.'


@pytest.fixture
def ru(qapp):
    return Translator('ru')


@pytest.fixture
def en(qapp):
    return Translator('en')


# Error codes reach job.error as literals raised directly, raised through SchoolAccessError,
# or picked by Instagram's _network_reason (its fallback argument and its returns).
CODE_PATTERNS = (
    re.compile(r"(?:MediaFailure|WorkFailed|SchoolAccessError)\(\s*'([a-z_]+)'"),
    re.compile(r"_network_reason\([^,()]+,\s*'([a-z_]+)'"),
    re.compile(r"return '((?:instagram|getcourse|youtube)_[a-z_]+)'"),
)


def source_error_codes():
    codes = {'no_output'}
    for path in SOURCE.rglob('*.py'):
        text = path.read_text(encoding='utf-8')
        for pattern in CODE_PATTERNS:
            codes.update(pattern.findall(text))
    return codes


def test_every_source_error_code_has_specific_text():
    codes = source_error_codes()
    assert len(codes) > 20
    assert {'instagram_rate_limited', 'getcourse_school_login_required'} <= codes
    missing = sorted(
        code for code in codes if code not in FAILURE_GROUPS.keys() | AUTH_SETTINGS_CODES
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
            {'media_filter': 'photo', 'format': 'mp3'},
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


class Recorder(QPainter):
    """Keeps every text the delegate draws and the pen colour it used."""

    def __init__(self, device):
        super().__init__(device)
        self.drawn = []

    def drawText(self, *args):  # noqa: N802 - overrides the Qt method
        self.drawn.append((args[-1], self.pen().color().name()))
        super().drawText(*args)


def seeded_window(make_window, tmp_path, *jobs):
    repository = SqliteJobRepository(tmp_path / 'status.sqlite3')
    for item in jobs:
        repository.add(item)
    window, _ = make_window(repository=repository)
    return window


def painted(window, row=0):
    view = window.queue_view
    index = view.model().index(row, 0)
    option = QStyleOptionViewItem()
    option.rect = view.visualRect(index)
    option.font = view.font()
    pixmap = QPixmap(option.rect.size() + QSize(1, 1))
    painter = Recorder(pixmap)
    try:
        view.itemDelegate().paint(painter, option, index)
    finally:
        painter.end()
    return painter.drawn


def failed(code, url=INSTAGRAM, identity='bad'):
    request = DownloadRequest(parse_url(url), DownloadOptions(Path.home()))
    return Job(identity, request, JobState.FAILED, error=code)


def tooltip(window, row=0):
    return window.queue_view.model().index(row, 0).data(Qt.ItemDataRole.ToolTipRole)


def test_failed_row_tooltip_has_reason_and_code(make_window, tmp_path):
    window = seeded_window(make_window, tmp_path, failed('auth_required'))
    assert tooltip(window) == 'Нужен вход в Instagram. Откройте «Аккаунты».\nКод: auth_required'


def test_failed_row_second_line_is_reason(make_window, tmp_path):
    done = Job(
        'ok', DownloadRequest(parse_url(YOUTUBE), DownloadOptions(Path.home())), JobState.COMPLETED
    )
    window = seeded_window(make_window, tmp_path, failed('tool_missing'), done)
    delegate = window.queue_view.itemDelegate()
    rows = {window.queue_view.model().index(n, 0).data(JobListModel.JobIdRole): n for n in (0, 1)}
    reason = 'Не найден FFmpeg. Переустановите ClipFlow.'
    assert delegate.second_line(failed('tool_missing')) == reason
    assert delegate.second_line(done) == 'YouTube  ·  MP4  ·  Лучшее качество'
    error = window.theme.tokens()['error']
    assert (reason, error) in painted(window, rows['bad'])
    assert ('YouTube  ·  MP4  ·  Лучшее качество', window.theme.tokens()['muted']) in painted(
        window, rows['ok']
    )
    assert tooltip(window, rows['ok']) == window.queue_view.model().index(rows['ok'], 0).data(
        JobListModel.TitleRole
    )


def test_reason_follows_language_switch(make_window, tmp_path):
    window = seeded_window(make_window, tmp_path, failed('auth_required'))
    window.tr.set_language('en')
    assert (
        tooltip(window) == 'Sign-in to Instagram is required. Open Accounts.\nCode: auth_required'
    )
    assert any(text.startswith('Sign-in to Instagram') for text, _ in painted(window))


def test_long_reason_is_elided_in_narrow_window(make_window, tmp_path, qtbot):
    code = 'instagram_item_failed:003:instagram_invalid_metadata'
    window = seeded_window(make_window, tmp_path, failed(code))
    window.resize(880, 700)
    qtbot.wait(50)
    full = window.queue_view.itemDelegate().second_line(failed(code))
    shown = [text for text, _ in painted(window) if text.endswith('…')]
    assert len(shown) == 1 and full.startswith(shown[0][:-1]) and shown[0] != full
