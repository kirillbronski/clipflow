"""Rows as in 4K: a cover on the left, the file's details below the title, «⋮» on the right."""

from pathlib import Path

from PySide6.QtCore import QEvent, QPointF, QRect, QSize, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPixmap
from PySide6.QtWidgets import QStyleOptionViewItem

from clipflow.domain.models import DownloadOptions, DownloadRequest, Job, JobState, MediaDetails
from clipflow.domain.urls import parse_url
from clipflow.ui.job_status import SEPARATOR
from clipflow.ui.queue_delegate import QueueDelegate
from clipflow.ui.queue_model import JobListModel

PLAYLIST = 'https://www.youtube.com/playlist?list=PLgroup'


def job(identity, state=JobState.QUEUED, parent=None, url=None, details=None):
    request = DownloadRequest(
        parse_url(url or 'https://youtu.be/' + identity), DownloadOptions(Path('/d'))
    )
    return Job(identity, request, state=state, parent_id=parent, details=details)


def cover(color='#00ff00'):
    pixmap = QPixmap(160, 90)
    pixmap.fill(QColor(color))
    return pixmap


def option(width=800):
    item = QStyleOptionViewItem()
    item.rect = QRect(0, 0, width, 96)
    return item


def render(model, row=0):
    delegate = QueueDelegate()
    pixmap = QPixmap(QSize(801, 97))
    pixmap.fill(QColor('#000000'))
    painter = Texts(pixmap)
    try:
        delegate.paint(painter, option(), model.index(row))
    finally:
        painter.end()
    return pixmap.toImage(), painter.drawn


class Texts(QPainter):
    def __init__(self, device):
        super().__init__(device)
        self.drawn = []

    def drawText(self, *args):
        self.drawn.append(args[-1])
        super().drawText(*args)


def click(delegate, model, point, row=0):
    point = QPointF(point)
    event = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        point,
        point,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    return delegate.editorEvent(event, model, option(), model.index(row))


def test_row_with_cover_paints_cover(qapp):
    model = JobListModel([job('a')])
    model.covers = lambda job_id: cover()
    image, _ = render(model)
    # Near the cover's corner, away from the play mark in its middle.
    assert image.pixelColor(10, 33) == QColor('#00ff00')


def test_row_without_cover_keeps_badge(qapp):
    model = JobListModel([job('a')])
    model.covers = lambda job_id: None
    image, drawn = render(model)
    assert image.pixelColor(10, 33) != QColor('#00ff00')
    assert '▷' in drawn


def test_menu_button_emits_row_menu_and_no_cancel_cross(qapp):
    model = JobListModel([job('a', JobState.DOWNLOADING)])
    delegate = QueueDelegate()
    seen = []
    delegate.action_requested.connect(lambda *args: seen.append(args))
    item = option()
    _, secondary = delegate._buttons(item.rect.adjusted(0, 0, -2, 0))
    assert click(delegate, model, secondary.center())
    assert seen == [('a', 'row_menu')]
    _, drawn = render(model)
    assert '⋮' in drawn
    assert '×' not in drawn


def test_menu_button_on_finished_rows_too(qapp):
    model = JobListModel([job('a', JobState.COMPLETED)])
    delegate = QueueDelegate()
    seen = []
    delegate.action_requested.connect(lambda *args: seen.append(args))
    item = option()
    _, secondary = delegate._buttons(item.rect.adjusted(0, 0, -2, 0))
    assert click(delegate, model, secondary.center())
    assert seen == [('a', 'row_menu')]


def test_cover_pixmaps_are_cached(qapp):
    jobs = [job(f'j{n}') for n in range(700)]
    model = JobListModel(jobs)
    loads = []

    def covers(job_id):
        loads.append(job_id)
        return cover()

    model.covers = covers
    for _ in range(2):
        for row in range(0, 700, 70):
            model.index(row).data(JobListModel.CoverRole)
    assert len(loads) == len(set(loads)) == 10


def test_cover_cache_drops_on_change(qapp):
    model = JobListModel([job('a')])
    covers = {'a': None}
    model.covers = covers.get
    assert model.index(0).data(JobListModel.CoverRole) is None
    covers['a'] = cover()
    model.cover_changed('a')
    assert model.index(0).data(JobListModel.CoverRole).cacheKey() == covers['a'].cacheKey()


def test_group_row_uses_first_member_cover(qapp):
    model = JobListModel([job('p', url=PLAYLIST), job('c0', parent='p'), job('c1', parent='p')])
    member = cover('#0000ff')
    model.covers = {'c1': member}.get
    assert model.index(0).data(JobListModel.CoverRole).cacheKey() == member.cacheKey()
    own = cover()
    model.covers = {'p': own, 'c1': member}.get
    model.cover_changed('p')
    assert model.index(0).data(JobListModel.CoverRole).cacheKey() == own.cacheKey()


def test_details_line_replaces_meta_text(qapp):
    details = MediaDetails(duration=117.0, height=1080, author='Автор')
    model = JobListModel([job('a', details=details), job('b')])
    _, drawn = render(model)
    assert SEPARATOR.join(['1:57', 'MP4', '1080p', 'Автор']) in drawn
    _, drawn = render(model, 1)
    assert any(text.startswith('YouTube') for text in drawn)


class Sizes(QPainter):
    def __init__(self, device):
        super().__init__(device)
        self.sizes = {}

    def drawText(self, *args):
        self.sizes[args[-1]] = self.font().pixelSize()
        super().drawText(*args)


def test_row_buttons_match_group_buttons(qapp):
    model = JobListModel(
        [job('a', JobState.COMPLETED), job('p', url=PLAYLIST), job('c', parent='p')]
    )
    sizes = {}
    for row in (0, 1):
        pixmap = QPixmap(QSize(801, 97))
        painter = Sizes(pixmap)
        try:
            QueueDelegate().paint(painter, option(), model.index(row))
        finally:
            painter.end()
        sizes[row] = painter.sizes
    assert sizes[0]['⋮'] == sizes[1]['⋮'] == 17
    assert sizes[0]['↗'] == 17
