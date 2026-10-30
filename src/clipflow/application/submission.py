"""One submission command for typed links, mixed batches and profile requests."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from urllib.parse import parse_qs, urlencode, urlparse
from uuid import uuid4

from clipflow.domain.models import (
    ContentKind,
    DownloadOptions,
    DownloadRequest,
    Job,
    Service,
    TERMINAL_STATES,
)
from clipflow.domain.urls import InvalidLink, parse_url, request_key
from .ports import JobRepository


@dataclass(frozen=True)
class LineError:
    line: int
    safe_input: str
    message: str


@dataclass(frozen=True)
class BatchPreview:
    requests: tuple[DownloadRequest, ...]
    invalid: tuple[LineError, ...]
    duplicate_lines: tuple[int, ...]


@dataclass(frozen=True)
class SubmissionResult:
    added: tuple[str, ...]
    existing: tuple[str, ...]


def _safe_input(text: str) -> str:
    try:
        parsed = urlparse(text)
        if parsed.username or parsed.password:
            return parsed._replace(netloc=parsed.hostname or '', query='', fragment='').geturl()
    except ValueError:
        return '[invalid URL]'
    return text


class SubmissionService:
    def __init__(self, repository: JobRepository):
        self.repository = repository

    def preview(
        self,
        text: str,
        presets: Mapping[Service, DownloadOptions],
        mode: str = 'batch',
        profile_limit: int | None = 10,
    ) -> BatchPreview:
        if mode not in {'single', 'batch', 'profile', 'playlist', 'lesson'}:
            raise ValueError('Unsupported submission mode')
        requests, invalid, duplicates = [], [], []
        seen = set()
        lines = [
            (number, line.strip())
            for number, line in enumerate(text.splitlines(), 1)
            if line.strip()
        ]
        if mode != 'batch' and len(lines) > 1:
            return BatchPreview(
                (), (LineError(1, '', 'Use multiple-links mode for more than one link'),), ()
            )
        for number, raw in lines:
            try:
                link = parse_url(raw)
                if mode == 'playlist':
                    playlist_id = parse_qs(urlparse(raw).query).get('list', [''])[0]
                    if link.service != Service.YOUTUBE or not playlist_id:
                        raise InvalidLink('Expected a YouTube playlist link')
                    origin = 'music.youtube.com' if link.is_music else 'www.youtube.com'
                    link = parse_url(
                        'https://' + origin + '/playlist?' + urlencode({'list': playlist_id})
                    )
                if mode == 'single' and link.kind in {ContentKind.PROFILE, ContentKind.PLAYLIST}:
                    raise InvalidLink('Choose profile or playlist mode explicitly')
                if mode == 'profile' and link.kind != ContentKind.PROFILE:
                    raise InvalidLink('Expected an Instagram profile')
                if mode == 'lesson' and link.service != Service.GETCOURSE:
                    raise InvalidLink('Expected a GetCourse lesson')
                options = presets[link.service]
                is_profile = link.kind == ContentKind.PROFILE
                if is_profile:
                    options = replace(options, post_folder=True)
                request = DownloadRequest(
                    link, options, profile_limit=profile_limit if is_profile else None
                )
                key = request_key(request)
                if key in seen:
                    duplicates.append(number)
                else:
                    seen.add(key)
                    requests.append(request)
            except (InvalidLink, ValueError, KeyError) as error:
                invalid.append(LineError(number, _safe_input(raw), str(error)))
        return BatchPreview(tuple(requests), tuple(invalid), tuple(duplicates))

    def submit(self, preview: BatchPreview) -> SubmissionResult:
        added, existing = [], []
        # Prefer an active equivalent over an older completed copy when both exist.
        candidates = sorted(self.repository.list(), key=lambda job: job.state in TERMINAL_STATES)
        index = {}
        for job in candidates:
            index.setdefault(request_key(job.request), job.id)
        for request in preview.requests:
            key = request_key(request)
            if key in index:
                existing.append(index[key])
                continue
            job = Job(str(uuid4()), request)
            self.repository.add(job)
            index[key] = job.id
            added.append(job.id)
        return SubmissionResult(tuple(added), tuple(existing))

    def repeat(self, job_id: str) -> str:
        original = self.repository.get(job_id)
        if original.state not in TERMINAL_STATES:
            raise ValueError('This job is already queued or active')
        job = Job(str(uuid4()), original.request, parent_id=original.parent_id)
        self.repository.add(job)
        return job.id
