"""Painted compact rows and hit targets; no per-row QPushButtons."""

from PySide6.QtCore import QRect, QSize, Qt, Signal, QEvent
from PySide6.QtGui import QColor, QFont, QPen
from PySide6.QtWidgets import QStyledItemDelegate, QStyle

from clipflow.domain.models import JobState, TERMINAL_STATES
from clipflow.ui.queue_model import JobListModel
from clipflow.ui.i18n import Translator
from clipflow.ui.themes import PALETTES
from clipflow.ui.history import result_status

SOURCE_NAMES = {'youtube': 'YouTube', 'instagram': 'Instagram', 'getcourse': 'GetCourse'}


class QueueDelegate(QStyledItemDelegate):
    action_requested = Signal(str, str)

    def __init__(self, parent=None, *, theme=None, translator=None):
        super().__init__(parent)
        self.theme = theme
        self.tr = translator or Translator(parent=self)

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
        badge = QRect(rect.left(), rect.top() + 21, 47, 54)
        tint = QColor(t[job.request.link.service.value])
        tint.setAlpha(28)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(tint)
        painter.drawRoundedRect(badge, 6, 6)
        painter.setPen(QColor(t[job.request.link.service.value]))
        font = QFont(option.font)
        font.setPixelSize(18)
        painter.setFont(font)
        painter.drawText(
            badge,
            Qt.AlignmentFlag.AlignCenter,
            '▧' if job.request.options.media_filter == 'photo' else '▷',
        )
        left = rect.left() + 60
        available = max(50, rect.width() - 230)
        title_rect = QRect(left, rect.top() + 16, available, 23)
        font.setPixelSize(13)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(foreground))
        painter.drawText(
            title_rect,
            Qt.AlignmentFlag.AlignVCenter,
            painter.fontMetrics().elidedText(
                index.data(JobListModel.TitleRole), Qt.TextElideMode.ElideRight, available
            ),
        )
        font.setPixelSize(11)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor(muted))
        quality = (
            f'{job.request.options.max_height}p'
            if job.request.options.max_height
            else self.tr.text('best_quality')
        )
        meta = f'{SOURCE_NAMES[job.request.link.service.value]}  ·  {job.request.options.format.upper()}  ·  {quality}'
        painter.drawText(
            QRect(left, rect.top() + 39, available, 19),
            Qt.AlignmentFlag.AlignVCenter,
            painter.fontMetrics().elidedText(meta, Qt.TextElideMode.ElideRight, available),
        )
        progress = index.data(JobListModel.ProgressRole)
        label = self.tr.text('state_' + job.state.value)
        if result_status(job) == 'files_missing':
            label = self.tr.text('files_missing')
        if job.source_required:
            label = self.tr.text('source_needed')
        elif job.pause_reason == 'selection_required':
            label = self.tr.text('selection_needed')
        elif job.pause_reason in {'rate_limit', 'rate_spacing'}:
            label = self.tr.text('instagram_wait')
            if job.next_allowed_at:
                label += ' · ' + job.next_allowed_at.astimezone().strftime('%H:%M')
        elif progress and job.state == JobState.DOWNLOADING:
            label = (
                f'{min(99, int(progress.downloaded_bytes / progress.total_bytes * 100))}%'
                if progress.total_bytes
                else f'{progress.downloaded_bytes / 1048576:.1f} ' + self.tr.text('mb')
            )
            if progress.speed_bytes_per_second:
                label += f' · {progress.speed_bytes_per_second / 1048576:.1f} ' + self.tr.text(
                    'mb_s'
                )
        painter.setPen(
            QColor(
                foreground
                if selected
                else t['muted']
                if result_status(job) == 'files_missing'
                else t['success']
                if job.state == JobState.COMPLETED
                else t['error']
                if job.state == JobState.FAILED
                else t['muted']
            )
        )
        active_progress = (
            progress
            and progress.total_bytes
            and job.state in {JobState.DOWNLOADING, JobState.PROCESSING, JobState.PAUSED}
        )
        painter.drawText(
            QRect(rect.right() - 235, rect.top() + (59 if active_progress else 25), 146, 26),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            label,
        )
        if (
            progress
            and progress.total_bytes
            and job.state in {JobState.DOWNLOADING, JobState.PROCESSING, JobState.PAUSED}
        ):
            bar = QRect(left, rect.top() + 71, max(20, rect.width() - 310), 3)
            painter.fillRect(bar, QColor(t['border']))
            width = int(
                bar.width() * max(0, min(0.99, progress.downloaded_bytes / progress.total_bytes))
            )
            painter.fillRect(
                QRect(bar.left(), bar.top(), width, bar.height()),
                QColor(t[job.request.link.service.value]),
            )
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
        painter.restore()

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
