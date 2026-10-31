"""Painted compact rows and hit targets; no per-row QPushButtons."""

from PySide6.QtCore import QEvent, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPen
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from clipflow.application.history import result_status
from clipflow.domain.models import TERMINAL_STATES, JobState
from clipflow.ui.i18n import Translator
from clipflow.ui.job_status import error_text, meta_text
from clipflow.ui.queue_model import JobListModel
from clipflow.ui.themes import PALETTES


class QueueDelegate(QStyledItemDelegate):
    action_requested = Signal(str, str)

    def __init__(self, parent=None, *, theme=None, translator=None):
        super().__init__(parent)
        self.theme = theme
        self.tr = translator or Translator(parent=self)

    def second_line(self, job):
        """The failure reason for a failed job, otherwise its source and quality."""
        if job.state == JobState.FAILED:
            return error_text(job.error, job.request.link.service, self.tr)
        return meta_text(job, self.tr)

    def sizeHint(self, option, index):
        return QSize(400, 96)

    @staticmethod
    def _buttons(rect):
        return QRect(rect.right() - 78, rect.top() + 26, 30, 30), QRect(
            rect.right() - 40, rect.top() + 26, 30, 30
        )

    def paint(self, painter, option, index):
        job = index.data(JobListModel.JobRole)
        if job is None:
            return
        t = self.theme.tokens() if self.theme else PALETTES['dark']
        painter.save()
        rect = option.rect.adjusted(0, 0, -2, 0)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if selected:
            painter.fillRect(rect, QColor(t['selection']))
        foreground = t['selection_text'] if selected else t['text']
        muted = t['selection_text'] if selected else t['muted']
        painter.setPen(QColor(t['border']))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        font = QFont(option.font)
        self._paint_badge(painter, font, rect, job, t)
        left = rect.left() + 60
        available = max(50, rect.width() - 230)
        font.setPixelSize(13)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(foreground))
        painter.drawText(
            QRect(left, rect.top() + 16, available, 23),
            Qt.AlignmentFlag.AlignVCenter,
            painter.fontMetrics().elidedText(
                index.data(JobListModel.TitleRole), Qt.TextElideMode.ElideRight, available
            ),
        )
        font.setPixelSize(11)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(
            QColor(t['error'] if job.state == JobState.FAILED and not selected else muted)
        )
        painter.drawText(
            QRect(left, rect.top() + 39, available, 19),
            Qt.AlignmentFlag.AlignVCenter,
            painter.fontMetrics().elidedText(
                self.second_line(job), Qt.TextElideMode.ElideRight, available
            ),
        )
        progress = index.data(JobListModel.ProgressRole)
        active_progress = bool(
            progress
            and progress.total_bytes
            and job.state in {JobState.DOWNLOADING, JobState.PROCESSING, JobState.PAUSED}
        )
        painter.setPen(QColor(foreground if selected else _status_color(job, t)))
        painter.drawText(
            QRect(rect.right() - 235, rect.top() + (59 if active_progress else 25), 146, 26),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            self.status_text(job, progress),
        )
        if active_progress:
            self._paint_progress(
                painter, QRect(left, rect.top() + 71, 0, 3), rect, job, t, progress
            )
        self._paint_buttons(painter, rect, job, muted)
        painter.restore()

    @staticmethod
    def _paint_badge(painter, font, rect, job, t):
        badge = QRect(rect.left(), rect.top() + 21, 47, 54)
        tint = QColor(t[job.request.link.service.value])
        tint.setAlpha(28)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(tint)
        painter.drawRoundedRect(badge, 6, 6)
        painter.setPen(QColor(t[job.request.link.service.value]))
        font.setPixelSize(18)
        painter.setFont(font)
        painter.drawText(
            badge,
            Qt.AlignmentFlag.AlignCenter,
            '▧' if job.request.options.media_filter == 'photo' else '▷',
        )

    @staticmethod
    def _paint_progress(painter, origin, rect, job, t, progress):
        bar = QRect(origin.left(), origin.top(), max(20, rect.width() - 310), 3)
        painter.fillRect(bar, QColor(t['border']))
        width = int(
            bar.width() * max(0, min(0.99, progress.downloaded_bytes / progress.total_bytes))
        )
        painter.fillRect(
            QRect(bar.left(), bar.top(), width, bar.height()),
            QColor(t[job.request.link.service.value]),
        )

    def _paint_buttons(self, painter, rect, job, muted):
        primary, secondary = self._buttons(rect)
        painter.setPen(QPen(QColor(muted), 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        glyph = (
            '↗'
            if job.state == JobState.COMPLETED
            else 'Ⅱ'
            if job.state in {JobState.PROBING, JobState.DOWNLOADING, JobState.PROCESSING}
            else '▷'
        )
        painter.drawText(primary, Qt.AlignmentFlag.AlignCenter, glyph)
        if job.state not in TERMINAL_STATES:
            painter.drawText(secondary, Qt.AlignmentFlag.AlignCenter, '×')

    def status_text(self, job, progress):
        """The short state at the right of a row: waiting reasons, percent and speed."""
        if job.source_required:
            return self.tr.text('source_needed')
        if job.pause_reason == 'selection_required':
            return self.tr.text('selection_needed')
        if job.pause_reason in {'rate_limit', 'rate_spacing'}:
            label = self.tr.text('instagram_wait')
            if job.next_allowed_at:
                label += ' · ' + job.next_allowed_at.astimezone().strftime('%H:%M')
            return label
        if progress and job.state == JobState.DOWNLOADING:
            return self._transfer_text(progress)
        if result_status(job) == 'files_missing':
            return self.tr.text('files_missing')
        return self.tr.text('state_' + job.state.value)

    def _transfer_text(self, progress):
        label = (
            f'{min(99, int(progress.downloaded_bytes / progress.total_bytes * 100))}%'
            if progress.total_bytes
            else f'{progress.downloaded_bytes / 1048576:.1f} ' + self.tr.text('mb')
        )
        if progress.speed_bytes_per_second:
            mb_s = progress.speed_bytes_per_second / 1048576
            label += f' · {mb_s:.1f} ' + self.tr.text('mb_s')
        return label

    def editorEvent(self, event, model, option, index):
        if (
            event.type() == QEvent.Type.MouseButtonRelease
            and event.button() == Qt.MouseButton.LeftButton
        ):
            primary, secondary = self._buttons(option.rect.adjusted(0, 0, -2, 0))
            if primary.contains(event.position().toPoint()):
                self.action_requested.emit(index.data(JobListModel.JobIdRole), 'toggle')
                return True
            if (
                secondary.contains(event.position().toPoint())
                and index.data(JobListModel.JobRole).state not in TERMINAL_STATES
            ):
                self.action_requested.emit(index.data(JobListModel.JobIdRole), 'cancel')
                return True
        return super().editorEvent(event, model, option, index)


def _status_color(job, t):
    if result_status(job) == 'files_missing':
        return t['muted']
    if job.state == JobState.COMPLETED:
        return t['success']
    if job.state == JobState.FAILED:
        return t['error']
    return t['muted']
