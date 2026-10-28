"""Painted compact rows and hit targets; no per-row QPushButtons."""
from PySide6.QtCore import QRect,QSize,Qt,Signal,QEvent
from PySide6.QtGui import QColor,QFont,QPen
from PySide6.QtWidgets import QStyledItemDelegate,QStyle

from clipflow.domain.models import JobState,TERMINAL_STATES
from clipflow.ui.queue_model import JobListModel

SOURCE_NAMES={'youtube':'YouTube','instagram':'Instagram','getcourse':'GetCourse'}
SOURCE_COLORS={'youtube':'#ed6262','instagram':'#d45b9f','getcourse':'#58ad94'}
STATES={JobState.QUEUED:'В очереди',JobState.PROBING:'Проверка ссылки',JobState.DOWNLOADING:'Скачивание',
        JobState.PROCESSING:'Обработка',JobState.COMPLETED:'Готово',JobState.PAUSED:'На паузе',
        JobState.FAILED:'Не удалось скачать',JobState.CANCELLED:'Отменено'}


class QueueDelegate(QStyledItemDelegate):
    action_requested=Signal(str,str)

    def sizeHint(self,option,index): return QSize(400,88)

    @staticmethod
    def _buttons(rect):
        return QRect(rect.right()-78,rect.top()+26,30,30),QRect(rect.right()-40,rect.top()+26,30,30)

    def paint(self,painter,option,index):
        job=index.data(JobListModel.JobRole)
        if job is None: return
        painter.save(); rect=option.rect.adjusted(0,0,-2,0)
        if option.state & QStyle.StateFlag.State_Selected: painter.fillRect(rect,QColor('#292639'))
        painter.setPen(QColor('#30323d')); painter.drawLine(rect.bottomLeft(),rect.bottomRight())
        badge=QRect(rect.left()+8,rect.top()+20,42,46)
        painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(QColor('#333743')); painter.drawRoundedRect(badge,7,7)
        painter.setPen(QColor(SOURCE_COLORS[job.request.link.service.value])); font=QFont(option.font); font.setPointSize(15)
        painter.setFont(font); painter.drawText(badge,Qt.AlignmentFlag.AlignCenter,'↓')
        left=rect.left()+64; available=max(50,rect.width()-285)
        title_rect=QRect(left,rect.top()+16,available,23)
        font.setPointSize(10); font.setBold(True); painter.setFont(font); painter.setPen(QColor('#f0eff6'))
        painter.drawText(title_rect,Qt.AlignmentFlag.AlignVCenter,painter.fontMetrics().elidedText(index.data(JobListModel.TitleRole),Qt.TextElideMode.ElideRight,available))
        font.setPointSize(9); font.setBold(False); painter.setFont(font); painter.setPen(QColor('#aaa9ba'))
        quality=f'{job.request.options.max_height}p' if job.request.options.max_height else 'Лучшее качество'
        meta=f'{SOURCE_NAMES[job.request.link.service.value]}  ·  {job.request.options.format.upper()}  ·  {quality}'
        painter.drawText(QRect(left,rect.top()+39,available,19),Qt.AlignmentFlag.AlignVCenter,
                         painter.fontMetrics().elidedText(meta,Qt.TextElideMode.ElideRight,available))
        progress=index.data(JobListModel.ProgressRole)
        label=STATES[job.state]
        if job.source_required: label='Нужна ссылка'
        elif job.pause_reason=='selection_required': label='Выберите видео'
        elif job.pause_reason in {'rate_limit','rate_spacing'}:
            label='Ожидание Instagram'
            if job.next_allowed_at: label+=' · '+job.next_allowed_at.astimezone().strftime('%H:%M')
        elif progress and job.state==JobState.DOWNLOADING:
            label=(f'{min(99,int(progress.downloaded_bytes/progress.total_bytes*100))}%' if progress.total_bytes else
                   f'{progress.downloaded_bytes/1048576:.1f} МБ')
            if progress.speed_bytes_per_second: label+=f' · {progress.speed_bytes_per_second/1048576:.1f} МБ/с'
        painter.setPen(QColor('#6bc5a6') if job.state==JobState.COMPLETED else QColor('#e88888') if job.state==JobState.FAILED else QColor('#b4b1c4'))
        painter.drawText(QRect(rect.right()-235,rect.top()+25,146,32),Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter,label)
        if progress and progress.total_bytes and job.state in {JobState.DOWNLOADING,JobState.PROCESSING,JobState.PAUSED}:
            bar=QRect(left,rect.top()+67,max(20,rect.width()-170),3)
            painter.fillRect(bar,QColor('#393b49'))
            width=int(bar.width()*max(0,min(.99,progress.downloaded_bytes/progress.total_bytes)))
            painter.fillRect(QRect(bar.left(),bar.top(),width,bar.height()),QColor('#9b88f5'))
        primary,secondary=self._buttons(rect)
        painter.setPen(QPen(QColor('#c7c2dd'),1.5)); painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(primary,6,6)
        glyph='↗' if job.state==JobState.COMPLETED else 'Ⅱ' if job.state in {JobState.PROBING,JobState.DOWNLOADING,JobState.PROCESSING} else '▷'
        painter.drawText(primary,Qt.AlignmentFlag.AlignCenter,glyph)
        if job.state not in TERMINAL_STATES:
            painter.drawRoundedRect(secondary,6,6); painter.drawText(secondary,Qt.AlignmentFlag.AlignCenter,'×')
        painter.restore()

    def editorEvent(self,event,model,option,index):
        if event.type()==QEvent.Type.MouseButtonRelease and event.button()==Qt.MouseButton.LeftButton:
            primary,secondary=self._buttons(option.rect.adjusted(0,0,-2,0))
            if primary.contains(event.position().toPoint()):
                self.action_requested.emit(index.data(JobListModel.JobIdRole),'toggle'); return True
            if secondary.contains(event.position().toPoint()) and index.data(JobListModel.JobRole).state not in TERMINAL_STATES:
                self.action_requested.emit(index.data(JobListModel.JobIdRole),'cancel'); return True
        return super().editorEvent(event,model,option,index)
