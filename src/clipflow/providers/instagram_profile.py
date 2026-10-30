"""Profile discovery: deduplicate feed/Reels and prove completeness before latest N."""

from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import datetime
import re
from typing import Protocol
from datetime import timezone
import hashlib
import instaloader
from instaloader import InstaloaderContext
from copy import copy

from clipflow.domain.events import RequestsDiscovered, StageChanged, WorkCancelled
from clipflow.domain.models import ContentKind, Service, JobState, DownloadRequest
from clipflow.domain.urls import parse_url, request_key
from clipflow.providers.base import DownloadResult, ProbeResult, MediaFailure
from clipflow.application.instagram_rate_policy import gated_request, InstagramDeferred
from clipflow.providers.access import open_downloader
from clipflow.providers.media import _QuietLogger


@dataclass(frozen=True)
class PostRef:
    code: str
    published_at: datetime
    author: str
    caption: str | None = None

    def __post_init__(self):
        if (
            not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', self.code)
            or self.published_at.tzinfo is None
            or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.]{0,29}', self.author)
        ):
            raise ValueError('Invalid profile post')


@dataclass(frozen=True)
class ProfilePage:
    posts: tuple[PostRef, ...]
    next_cursor: str | None
    order_guaranteed: bool
    pinned_ids: frozenset[str]


class ProfilePageSource(Protocol):
    def pages(self, request, context) -> Iterator[ProfilePage]: ...


class InstagramProfileProvider:
    def __init__(self, page_source):
        self.page_source = page_source

    def probe(self, request, context):
        context.cancel.raise_if_cancelled()
        if request.link.service != Service.INSTAGRAM or request.link.kind != ContentKind.PROFILE:
            raise MediaFailure('instagram_profile_required')
        if context.instagram_rate is None:
            raise MediaFailure('instagram_rate_policy_required')
        return ProbeResult((), ())

    def execute(self, request, context):
        self.probe(request, context)
        context.emit(StageChanged(JobState.PROBING))
        found = {}
        count = 0
        exhausted = False
        store = getattr(context.instagram_rate, 'store', None)
        key = request_key(request)

        def emit(posts):
            nonlocal count
            batch = []
            for post in posts:
                context.cancel.raise_if_cancelled()
                line = next((l.strip() for l in (post.caption or '').splitlines() if l.strip()), '')
                batch.append(
                    DownloadRequest(
                        parse_url(f'https://www.instagram.com/p/{post.code}/'),
                        replace(request.options, post_folder=True),
                        label=line[:100] or post.code,
                    )
                )
                if len(batch) == 25:
                    context.emit(RequestsDiscovered(tuple(batch)))
                    count += len(batch)
                    batch = []
            if batch:
                context.emit(RequestsDiscovered(tuple(batch)))
                count += len(batch)

        try:
            for page in self.page_source.pages(request, context):
                context.cancel.raise_if_cancelled()
                new = []
                for post in page.posts:
                    if post.code not in found:
                        found[post.code] = post
                        new.append(post)
                exhausted = page.next_cursor is None
                # Checkpoints are progress hints only, not a durable queue ACK.
                # Expired/unportable cursors are safely re-enumerated and deduped.
                if store:
                    store.checkpoint(key, page.next_cursor, found, False)
                if request.profile_limit is None:
                    emit(new)
            if not exhausted:
                raise MediaFailure('instagram_profile_incomplete')
            if request.profile_limit is not None:
                emit(
                    sorted(found.values(), key=lambda p: (p.published_at, p.code), reverse=True)[
                        : request.profile_limit
                    ]
                )
            if store:
                store.checkpoint(key, None, found, True)
            return DownloadResult((), count)
        except (WorkCancelled, MediaFailure):
            raise
        except Exception:
            raise MediaFailure('instagram_profile_failed') from None


class PacedSession:
    """Also wraps copies made internally by Instaloader's GraphQL/iPhone paths."""

    def __init__(self, session, context):
        self.session = session
        self.execution = context

    def __getattr__(self, name):
        return getattr(self.session, name)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.session.close()

    def get(self, url, **kwargs):
        return self.request('GET', url, **kwargs)

    def post(self, url, **kwargs):
        return self.request('POST', url, **kwargs)

    def request(self, method, url, **kwargs):
        with gated_request(self.execution, 'page'):
            self.execution.cancel.raise_if_cancelled()
            kwargs.setdefault('timeout', 30)
            kwargs['allow_redirects'] = False
            response = self.session.request(method, url, **kwargs)
            if response.status_code == 429:
                decision = self.execution.instagram_rate.record_429(
                    response.headers.get('Retry-After')
                )
                response.close()
                raise InstagramDeferred(decision)
            if response.status_code in {401, 403}:
                response.close()
                raise MediaFailure('instagram_access_required')
            self.execution.cancel.raise_if_cancelled()
            return response


class PacedContext(InstaloaderContext):
    def __init__(self, execution):
        self.execution = execution
        super().__init__(
            sleep=False,
            quiet=True,
            max_connection_attempts=1,
            request_timeout=30,
            fatal_status_codes=[401, 403, 429],
            rate_controller=lambda ctx: PacedController(ctx),
        )

    def get_anonymous_session(self):
        return PacedSession(super().get_anonymous_session(), self.execution)

    def log(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass

    def get_json(
        self,
        path,
        params,
        host='www.instagram.com',
        session=None,
        _attempt=1,
        response_headers=None,
        use_post=False,
    ):
        session = session if session is not None else self._session
        if not isinstance(session, PacedSession):
            session = PacedSession(session, self.execution)
        return super().get_json(path, params, host, session, _attempt, response_headers, use_post)


class PacedController(instaloader.RateController):
    def sleep(self, seconds):
        context = self._context.execution
        try:
            context.instagram_rate.library_wait(seconds, context.cancel)
        except InstagramDeferred as error:
            context.emit(error.decision)
            raise

    def handle_429(self, query_type):
        context = self._context.execution
        decision = context.instagram_rate.record_429(None)
        context.emit(decision)
        raise InstagramDeferred(decision)


class InstaloaderPageSource:
    """One reusable library controller/session; no session writes or raw cursor dumps.

    Public API cursors are not a stable serialized Instaloader iterator contract.
    Resume deliberately re-enumerates with queue dedup rather than trusting an
    expired cursor and calling a partial set complete.
    """

    def __init__(self):
        self._context = None
        self._fingerprint = None

    def close(self):
        if self._context is not None:
            self._context.close()
        self._context = None
        self._fingerprint = None

    def pages(self, request, context):
        context.cancel.raise_if_cancelled()
        try:
            options = dict(
                context.auth.options_for(request.options.auth_profile, request.link.canonical_url)
            )
            options.update(quiet=True, no_warnings=True, logger=_QuietLogger())
            with open_downloader(options, context=context) as ydl:
                cookies = [copy(c) for c in ydl.cookiejar]
            digest = hashlib.sha256(
                repr([(c.domain, c.path, c.name, c.value) for c in cookies]).encode()
            ).digest()
            fingerprint = (digest, id(context.instagram_rate))
            if fingerprint != self._fingerprint:
                self.close()
                self._context = PacedContext(context)
                self._fingerprint = fingerprint
                for cookie in cookies:
                    self._context._session.cookies.set_cookie(cookie)
            self._context.execution = context
            self._context._session.execution = context
            if cookies and self._context.username is None:
                self._context.username = self._context.test_login()
                if not self._context.username:
                    raise MediaFailure('instagram_access_required')
            profile = instaloader.Profile.from_username(self._context, request.link.canonical_id)
            if profile.is_private and not (profile.followed_by_viewer or profile.is_self):
                raise MediaFailure('instagram_access_required')
            batch = []
            page = 0
            for method in (profile.get_posts, profile.get_reels):
                for post in method():
                    context.cancel.raise_if_cancelled()
                    published = post.date_utc.replace(tzinfo=timezone.utc)
                    caption = getattr(
                        post, 'caption', None
                    )  # read from the already fetched node, no request
                    batch.append(
                        PostRef(
                            post.shortcode,
                            published,
                            request.link.canonical_id,
                            caption if isinstance(caption, str) else None,
                        )
                    )
                    if len(batch) == 25:
                        page += 1
                        yield ProfilePage(tuple(batch), f'page-{page}', False, frozenset())
                        batch = []
            yield ProfilePage(tuple(batch), None, False, frozenset())
        except (WorkCancelled, MediaFailure):
            raise
        except Exception:
            raise MediaFailure('instagram_profile_failed') from None
