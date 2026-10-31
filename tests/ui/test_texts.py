"""Interface text catalogue: both languages complete, no dead keys, wording from the UX review."""

import re
from pathlib import Path

import pytest
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel, QPushButton

from clipflow.domain.failures import AUTH_SETTINGS_CODES, FAILURE_GROUPS
from clipflow.domain.models import JobState, Service
from clipflow.infrastructure.auth import NativeAuthGateway
from clipflow.infrastructure.auth_process.sessions import AUTH_MODES
from clipflow.ui.i18n import CATALOG, Translator
from tests.ui.test_workbench import make_window

SOURCE = Path(__file__).resolve().parents[2] / 'src' / 'clipflow'
REMOVED = (
    'footer',
    'delete',
    'batch_button',
    'add',
)
LITERAL_KEYS = (
    re.compile(r"\b(?:tr|translator)\.text\(\s*'([\w.]+)'\s*[,)]"),
    re.compile(r"\.(?:widget|bind)\(\s*[^,()]+,\s*'([\w.]+)'\s*[,)]"),
)


def sources():
    return {path: path.read_text(encoding='utf-8') for path in SOURCE.rglob('*.py')}


def test_catalogue_languages_have_same_keys():
    assert CATALOG['ru'].keys() == CATALOG['en'].keys()


def test_removed_keys_are_gone_and_unreferenced():
    code = '\n'.join(text for path, text in sources().items() if path.name != 'i18n.py')
    for key in REMOVED:
        assert key not in CATALOG['ru'], key
        for pattern in LITERAL_KEYS:
            assert key not in pattern.findall(code), key


def test_every_referenced_key_exists():
    referenced = {
        key
        for text in sources().values()
        for pattern in LITERAL_KEYS
        for key in pattern.findall(text)
    }
    assert len(referenced) > 50
    assert sorted(referenced - CATALOG['ru'].keys()) == []


def test_every_key_family_is_complete():
    prefix = re.compile(r"\b(?:tr|translator)\.text\(\s*'([\w.]+)'\s*\+")
    used = {key for text in sources().values() for key in prefix.findall(text)}
    assert used == {'error.', 'job_error.', 'state_', 'filter_'}
    families = {
        'filter_': ('all', 'active', 'completed', 'failed'),
        'state_': tuple(state.value for state in JobState),
        'job_error.': tuple(set(FAILURE_GROUPS.values())),
        'error.': tuple(AUTH_SETTINGS_CODES),
    }
    missing = [
        p + name for p, names in families.items() for name in names if p + name not in CATALOG['ru']
    ]
    missing += [
        s.value + '_subtitle' for s in Service if s.value + '_subtitle' not in CATALOG['ru']
    ]
    assert missing == []


@pytest.mark.parametrize(
    ('key', 'russian', 'english'),
    [
        ('sources_label', 'Источники', 'Sources'),
        (
            'youtube_hint',
            'Видео, музыка и плейлисты YouTube. Ссылки YouTube Music сохраняются в MP3.',
            'YouTube videos, music and playlists. YouTube Music links are saved as MP3.',
        ),
        (
            'getcourse_hint',
            'Скачиваются только материалы, к которым у вас есть доступ.',
            'Only materials you have access to are downloaded.',
        ),
        ('auto_start', 'Скачивать сразу', 'Start immediately'),
        ('description_beside', 'Описание рядом с файлом', 'Save description beside file'),
        (
            'quality_pending',
            'Проверяем доступное качество… Добавить в очередь можно уже сейчас.',
            'Checking available quality… You can add to the queue now.',
        ),
        (
            'probe_cancelled',
            'Проверка остановлена, чтобы начать загрузку. Добавить в очередь можно уже сейчас.',
            'Quality check stopped to start a download. You can add to the queue now.',
        ),
        (
            'probe_unavailable',
            'Проверка качества сейчас недоступна. Добавить в очередь можно.',
            'Quality check is unavailable right now. You can still add to the queue.',
        ),
        ('auth_native_mode', 'Обычный', 'Standard'),
        ('auth_ipad51', 'Совместимость 1', 'Compatibility 1'),
        ('auth_ipad87', 'Совместимость 2', 'Compatibility 2'),
        (
            'school_scope_note',
            'Доступ — только к школе из этой ссылки. '
            'Для «Сессии браузера» войдите в школу и закройте браузер.',
            'Access applies only to the school in this link. '
            'For a browser session, sign into the school and close the browser.',
        ),
        (
            'import_old_profile_hint',
            'Старый профиль импортируется только для выбранной школы.',
            'An old profile is imported only for the selected school.',
        ),
    ],
)
def test_changed_texts(key, russian, english):
    assert (CATALOG['ru'][key], CATALOG['en'][key]) == (russian, english)


def test_sources_label_reads_as_one_word(make_window):
    window, _ = make_window()
    label = next(w for w in window.findChildren(QLabel) if w.text() == 'Источники')
    assert label.font().capitalization() == QFont.Capitalization.AllUppercase
    assert label.font().letterSpacing() > 0


def test_no_footer(make_window):
    window, _ = make_window()
    for language, phrase in (
        ('ru', 'Файлы сохраняются локально'),
        ('en', 'Files are saved locally'),
    ):
        window.tr.set_language(language)
        assert not [w for w in window.findChildren(QLabel) if phrase in w.text()]


def test_auth_modes_new_labels_same_data(qapp):
    assert [key for key, _ in AUTH_MODES] == [
        'Обычный Qt WebEngine',
        'Chrome на iPad · 51',
        'Chrome на iPad · 87',
    ]
    for language, labels in (
        ('ru', ['Обычный', 'Совместимость 1', 'Совместимость 2']),
        ('en', ['Standard', 'Compatibility 1', 'Compatibility 2']),
    ):
        tr = Translator(language)
        assert [tr.text(label) for _, label in AUTH_MODES] == labels


def test_import_button_tooltip(make_window, tmp_path):
    from clipflow.ui.accounts import GetCourseDialog

    window, _ = make_window()
    window.presenter.set_auth_gateway(NativeAuthGateway(tmp_path))
    window.accounts_button.click()
    window.accounts_page.sign_in_buttons[Service.GETCOURSE].click()
    dialog = next(d for d in window._dialogs if isinstance(d, GetCourseDialog))
    button = next(
        b for b in dialog.findChildren(QPushButton) if b.text() == 'Импортировать прежний профиль'
    )
    assert button.toolTip() == 'Старый профиль импортируется только для выбранной школы.'
    dialog.reject()
