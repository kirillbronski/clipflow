"""One model and painted delegate for any queue size; no widget per download."""
from PySide6.QtCore import QAbstractListModel,QModelIndex,Qt,QSortFilterProxyModel

from clipflow.domain.events import ProgressChanged,TitleChanged
from clipflow.domain.models import JobState,TERMINAL_STATES
from clipflow.ui.i18n import Translator


class JobListModel(QAbstractListModel):
    JobIdRole=int(Qt.ItemDataRole.UserRole)+1
    TitleRole=JobIdRole+1; StateRole=JobIdRole+2; ProgressRole=JobIdRole+3
    FilesRole=JobIdRole+4; SourceRole=JobIdRole+5; JobRole=JobIdRole+6

    def __init__(self,jobs=(),parent=None):
        super().__init__(parent)
        self.translator=Translator(parent=self)
        self.jobs=tuple(jobs); self._rows={job.id:n for n,job in enumerate(self.jobs)}
        self._titles={}; self._progress={}

    def rowCount(self,parent=QModelIndex()): return 0 if parent.isValid() else len(self.jobs)

    def roleNames(self):
        return {self.JobIdRole:b'job_id',self.TitleRole:b'title',self.StateRole:b'state',
                self.ProgressRole:b'progress',self.FilesRole:b'files',self.SourceRole:b'source',self.JobRole:b'job'}

    def data(self,index,role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0<=index.row()<len(self.jobs): return None
        job=self.jobs[index.row()]
        title=self._titles.get(job.id) or (job.result_files[0].stem if job.result_files else
              '@'+job.request.link.canonical_id if job.request.link.kind.value=='profile' else self.translator.text('new_download'))
        return {int(Qt.ItemDataRole.DisplayRole):title,self.TitleRole:title,self.JobIdRole:job.id,
                self.StateRole:job.state.value,self.ProgressRole:self._progress.get(job.id),
                self.FilesRole:job.result_files,self.SourceRole:job.request.link.service.value,
                self.JobRole:job,int(Qt.ItemDataRole.ToolTipRole):title}.get(role)

    def set_jobs(self,jobs):
        jobs=tuple(jobs)
        old_ids=tuple(job.id for job in self.jobs); new_ids=tuple(job.id for job in jobs)
        if old_ids==new_ids:
            self.jobs=jobs
            if jobs: self.dataChanged.emit(self.index(0),self.index(len(jobs)-1))
            return
        if new_ids[:len(old_ids)]==old_ids and len(jobs)>len(old_ids):
            self.beginInsertRows(QModelIndex(),len(old_ids),len(jobs)-1)
            self.jobs=jobs; self._rows={job.id:n for n,job in enumerate(jobs)}
            self.endInsertRows()
        else:
            self.beginResetModel(); self.jobs=jobs; self._rows={job.id:n for n,job in enumerate(jobs)}; self.endResetModel()

    def update_job(self,job,payload):
        row=self._rows.get(job.id)
        if row is None:
            self.set_jobs((*self.jobs,job)); row=self._rows[job.id]
        previous=self.jobs[row]
        if previous.attempt_id!=job.attempt_id: self._progress.pop(job.id,None)
        if isinstance(payload,TitleChanged): self._titles[job.id]=' '.join(payload.title.split())[:240]
        if isinstance(payload,ProgressChanged): self._progress[job.id]=payload
        jobs=list(self.jobs); jobs[row]=job; self.jobs=tuple(jobs)
        self.dataChanged.emit(self.index(row),self.index(row))


class QueueFilter(QSortFilterProxyModel):
    def __init__(self,model,parent=None):
        super().__init__(parent); self.service=None; self.history=False; self.setSourceModel(model)

    def show_source(self,service=None,history=False):
        self.beginFilterChange()
        self.service=service; self.history=history
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def filterAcceptsRow(self,row,parent):
        model=self.sourceModel(); job=model.data(model.index(row,0,parent),model.JobRole)
        return ((self.service is None or job.request.link.service.value==self.service)
                and (not self.history or job.state in TERMINAL_STATES))
