from concurrent.futures import ThreadPoolExecutor
from threading import get_ident

import pytest

from clipflow.providers.instagram_profile import InstagramProfileProvider, ProfilePage
from clipflow.providers.base import MediaFailure
from clipflow.domain.events import RequestsDiscovered
from tests.instagram_fixtures import context
from tests.unit.test_profile_discovery import Source, post, req, codes


def test_429_second_page_keeps_discovered_jobs_but_not_success(tmp_path):
    source=Source([ProfilePage((post(1),),'second',False,frozenset()),MediaFailure('instagram_rate_limited')])
    ctx,events,_=context()
    with pytest.raises(MediaFailure): InstagramProfileProvider(source).execute(req(tmp_path),ctx)
    assert codes(events)==['C1']


def test_5000_posts_on_worker_bounded_batches_and_no_duplicates(tmp_path):
    pages=[ProfilePage(tuple(post(i) for i in range(start,min(start+25,5000))),
                       str(start+25) if start+25<5000 else None,False,frozenset()) for start in range(0,5000,25)]
    source=Source(pages); ctx,events,_=context(); owner=get_ident()
    def run():
        assert get_ident()!=owner
        return InstagramProfileProvider(source).execute(req(tmp_path),ctx)
    with ThreadPoolExecutor(max_workers=1) as pool: result=pool.submit(run).result()
    assert result.discovered_count==5000 and len(set(codes(events)))==5000
    assert max(len(e.requests) for e in events if isinstance(e,RequestsDiscovered))<=25


def test_partial_profile_jobs_survive_scheduler_failure_and_retry_dedup(tmp_path):
    from clipflow.application.scheduler import Scheduler
    from clipflow.domain.events import JobEvent,WorkFailed,WorkFinished,FilesSaved
    from clipflow.domain.models import Job,JobState,ContentKind
    from clipflow.providers.base import ExecutionContext
    from tests.helpers import MemoryJobRepository
    from tests.instagram_fixtures import Gate,Auth
    from clipflow.domain.events import CancellationToken
    source=Source([ProfilePage((post(1),),'more',False,frozenset()),MediaFailure('instagram_profile_failed')])
    provider=InstagramProfileProvider(source); repo=MemoryJobRepository()
    class Executor:
        def start(self,job,emit):
            def send(event): emit(JobEvent(job.id,job.attempt_id,event))
            try:
                if job.request.link.kind==ContentKind.PROFILE:
                    provider.execute(job.request,ExecutionContext(CancellationToken(),send,Auth(),Gate()))
                else:
                    output=tmp_path/(job.request.link.canonical_id+'.png'); output.write_bytes(b'synthetic')
                    send(FilesSaved((output,)))
                send(WorkFinished())
            except MediaFailure as error: send(WorkFailed(error.code))
        def stop(self,*args): pass
    repo.add(Job('profile',req(tmp_path)))
    scheduler=Scheduler(repo,Executor()); scheduler.start()
    assert repo.get('profile').state==JobState.FAILED
    assert len(repo.list())==2 and repo.list()[1].state==JobState.COMPLETED
    source.values=[ProfilePage((post(1),post(2)),None,False,frozenset())]
    scheduler.retry('profile')
    assert len(repo.list())==3 and all(j.state==JobState.COMPLETED for j in repo.list())
