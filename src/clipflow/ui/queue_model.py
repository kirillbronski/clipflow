"""One model and painted delegate for any queue size; no widget per download."""

from PySide6.QtCore import QAbstractListModel, QModelIndex, QSortFilterProxyModel, Qt

from clipflow.application.groups import descendants, group_summary, is_group
from clipflow.application.queue_view import job_kind, normalize
from clipflow.domain.events import ProgressChanged, TitleChanged
from clipflow.domain.models import TERMINAL_STATES, JobState
from clipflow.ui.i18n import Translator
from clipflow.ui.job_status import error_tooltip


class JobListModel(QAbstractListModel):
    JobIdRole = int(Qt.ItemDataRole.UserRole) + 1
    TitleRole = JobIdRole + 1
    StateRole = JobIdRole + 2
    ProgressRole = JobIdRole + 3
    FilesRole = JobIdRole + 4
    SourceRole = JobIdRole + 5
    JobRole = JobIdRole + 6
    GroupRole = JobIdRole + 7
    CoverRole = JobIdRole + 8
    SizeRole = JobIdRole + 9

    def __init__(self, jobs=(), parent=None):
        super().__init__(parent)
        self.translator = Translator(parent=self)
        self.jobs = tuple(jobs)
        self._rows = {job.id: n for n, job in enumerate(self.jobs)}
        self._titles = {}
        self._progress = {}
        self._sizes = {}  # job id -> (result files, bytes); read from disk once per file set
        self.covers = None  # job id -> QPixmap | None, set when covers are available
        self._covers = {}  # asked once per job; cover_changed forgets an answer
        self._index()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.jobs)

    def roleNames(self):
        return {
            self.JobIdRole: b'job_id',
            self.CoverRole: b'cover',
            self.SizeRole: b'size',
            self.TitleRole: b'title',
            self.StateRole: b'state',
            self.ProgressRole: b'progress',
            self.FilesRole: b'files',
            self.SourceRole: b'source',
            self.JobRole: b'job',
            self.GroupRole: b'group',
        }

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.jobs):
            return None
        job = self.jobs[index.row()]
        title = self.title(job)
        return {
            int(Qt.ItemDataRole.DisplayRole): title,
            self.TitleRole: title,
            self.JobIdRole: job.id,
            self.StateRole: job.state.value,
            self.ProgressRole: self._progress.get(job.id),
            self.FilesRole: job.result_files,
            self.SourceRole: job.request.link.service.value,
            self.JobRole: job,
            self.GroupRole: self._summary(job) if role == self.GroupRole else None,
            self.CoverRole: self._cover(job) if role == self.CoverRole else None,
            self.SizeRole: self._size(job) if role == self.SizeRole else None,
            int(Qt.ItemDataRole.ToolTipRole): (
                self.translator.text(
                    'show_posts' if job.request.link.service.value == 'instagram' else 'show_tracks'
                )
                if job.id in self._groups
                else error_tooltip(job.error, job.request.link.service, self.translator)
                if job.state == JobState.FAILED
                else title
            ),
        }.get(role)

    def title(self, job):
        """The name a row shows: live title, saved file, label, or the profile's handle."""
        profile = (
            '@' + job.request.link.canonical_id
            if job.request.link.kind.value == 'profile'
            else None
        )
        return (
            self._titles.get(job.id)
            or (job.result_files[0].stem if job.result_files else None)
            or job.title
            or job.request.label
            or profile
            or self.translator.text('new_download')
        )

    def _index(self):
        """Group membership by id, rebuilt in one pass whenever the list of jobs changes."""
        groups = descendants(self.jobs)
        self._members = {key: tuple(j.id for j in value) for key, value in groups.items()}
        self._groups = {
            job.id for job in self.jobs if job.id in groups and is_group(job, bool(groups[job.id]))
        }
        self._top = {member: key for key, value in self._members.items() for member in value}
        self._sizes = {}  # files may have been deleted or replaced since the last list

    def members(self, group_id):
        return tuple(self.jobs[self._rows[i]] for i in self._members.get(group_id, ()))

    def group_of(self, job_id):
        return self._top.get(job_id)

    def is_group_row(self, row):
        return self.jobs[row].id in self._groups

    def _own_cover(self, job_id):
        if job_id not in self._covers:
            self._covers[job_id] = self.covers(job_id) if self.covers else None
        return self._covers[job_id]

    def _cover(self, job):
        """The job's cover; a group without its own shows its first member's."""
        own = self._own_cover(job.id)
        if own is not None or job.id not in self._groups:
            return own
        return next(
            (c for i in self._members.get(job.id, ()) if (c := self._own_cover(i)) is not None),
            None,
        )

    def cover_changed(self, job_id):
        self._covers.pop(job_id, None)
        for identity in (job_id, self._top.get(job_id)):
            row = self._rows.get(identity)
            if row is not None:
                self.dataChanged.emit(self.index(row), self.index(row))

    def _size(self, job):
        cached = self._sizes.get(job.id)
        if cached is None or cached[0] != job.result_files:
            total = 0
            for path in job.result_files:
                try:
                    total += path.stat().st_size
                except OSError:
                    continue
            cached = self._sizes[job.id] = (job.result_files, total)
        return cached[1]

    def current_label(self, job):
        """Title and percent of a member being worked on, for its group's row."""
        title = self._titles.get(job.id) or job.title or job.request.label
        progress = self._progress.get(job.id)
        percent = (
            min(99, int(progress.downloaded_bytes / progress.total_bytes * 100))
            if progress and progress.total_bytes
            else None
        )
        return title, percent

    def _summary(self, job):
        if job.id not in self._groups:
            return None
        members = self.members(job.id)
        sizes = {m.id: self._size(m) for m in members if m.state == JobState.COMPLETED}
        return group_summary(job, members, sizes)

    def set_jobs(self, jobs):
        jobs = tuple(jobs)
        old_ids = tuple(job.id for job in self.jobs)
        new_ids = tuple(job.id for job in jobs)
        if old_ids == new_ids:
            self.jobs = jobs
            self._index()
            if jobs:
                self.dataChanged.emit(self.index(0), self.index(len(jobs) - 1))
            return
        if new_ids[: len(old_ids)] == old_ids and len(jobs) > len(old_ids):
            self.beginInsertRows(QModelIndex(), len(old_ids), len(jobs) - 1)
            self.jobs = jobs
            self._rows = {job.id: n for n, job in enumerate(jobs)}
            self._index()
            self.endInsertRows()
        else:
            self.beginResetModel()
            self.jobs = jobs
            self._rows = {job.id: n for n, job in enumerate(jobs)}
            self._index()
            self.endResetModel()

    def update_job(self, job, payload):
        row = self._rows.get(job.id)
        if row is None:
            self.set_jobs((*self.jobs, job))
            row = self._rows[job.id]
        previous = self.jobs[row]
        if previous.attempt_id != job.attempt_id:
            self._progress.pop(job.id, None)
        if isinstance(payload, TitleChanged):
            self._titles[job.id] = ' '.join(payload.title.split())[:240]
        if isinstance(payload, ProgressChanged):
            self._progress[job.id] = payload
        jobs = list(self.jobs)
        jobs[row] = job
        self.jobs = tuple(jobs)
        self.dataChanged.emit(self.index(row), self.index(row))
        group = self._rows.get(self._top.get(job.id))
        if group is not None:
            self.dataChanged.emit(self.index(group), self.index(group))


KINDS = ('all', 'video', 'audio', 'photo', 'playlists')


class QueueFilter(QSortFilterProxyModel):
    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.service = None
        self.history = False
        self.status = 'all'
        self.kind = 'all'
        self.query = ''
        self.group_id = None
        self.setSourceModel(model)

    def show_status(self, status):
        if status not in {'all', 'active', 'completed', 'failed'}:
            raise ValueError('invalid_status')
        self.beginFilterChange()
        self.status = status
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def show_kind(self, kind):
        if kind not in KINDS:
            raise ValueError('invalid_kind')
        self.beginFilterChange()
        self.kind = kind
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def show_query(self, text):
        self.beginFilterChange()
        self.query = normalize(text)
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def show_source(self, service=None, history=False):
        self.beginFilterChange()
        self.service = service
        self.history = history
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def show_group(self, group_id=None):
        """None lists top-level rows (a group is one row); an id lists that group's members."""
        self.beginFilterChange()
        self.group_id = group_id
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def filterAcceptsRow(self, row, parent):
        return self._accepts(row, self.status)

    def count(self, status):
        """Rows the current screen would show under a status, with the kind and search applied."""
        return sum(self._accepts(row, status) for row in range(self.sourceModel().rowCount()))

    def _accepts(self, row, status):
        model = self.sourceModel()
        job = model.jobs[row]
        if self.group_id is not None:
            # «Плейлисты» inside a group means all its tracks.
            kind = None if self.kind == 'playlists' else self.kind
            return (
                model.group_of(job.id) == self.group_id
                and self._kind_matches(job, kind)
                and self._matches(job, status)
                and self._found(job)
            )
        if job.parent_id is not None:
            return False
        group = model.is_group_row(row)
        members = model.members(job.id) if group else ()
        if not members:
            kind_ok = self.kind in {'all', 'playlists'} if group else self._kind_matches(job)
            return kind_ok and self._matches(job, status) and self._found(job)
        if not self._service_matches(job):
            return False
        # A group shows when any member would: by status, kind and search alike.
        kind = None if self.kind == 'playlists' else self.kind
        itself = self._found(job)
        return any(
            self._kind_matches(m, kind) and self._matches(m, status) and (itself or self._found(m))
            for m in members
        )

    def _kind_matches(self, job, kind=False):
        kind = self.kind if kind is False else kind
        return kind in {None, 'all'} or (kind != 'playlists' and job_kind(job) == kind)

    def _found(self, job):
        if not self.query:
            return True
        author = job.details.author if job.details else None
        texts = (self.sourceModel().title(job), author, job.request.link.canonical_url)
        return any(self.query in normalize(text) for text in texts)

    def _service_matches(self, job):
        return self.service is None or job.request.link.service.value == self.service

    def _matches(self, job, status):
        return (
            self._service_matches(job)
            and (not self.history or job.state in TERMINAL_STATES)
            and (
                status == 'all'
                or status == 'active'
                and job.state not in TERMINAL_STATES
                or status == 'completed'
                and job.state == JobState.COMPLETED
                or status == 'failed'
                and job.state == JobState.FAILED
            )
        )
