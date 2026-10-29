"""Scoped yt-dlp transport; a lease covers the response body, not every chunk."""
from yt_dlp.networking.common import Response
from yt_dlp.networking.exceptions import HTTPError, RequestError
from yt_dlp.networking._urllib import UrllibRH, RedirectHandler

from clipflow.application.instagram_rate_policy import gated_request, InstagramDeferred
from clipflow.domain.events import WorkCancelled
from clipflow.providers.access import _CancellableDownloader


class _CancelledRequest(RequestError):
    def __init__(self,error):
        super().__init__('cancelled')
        self.stopped=error


class LeasedResponse(Response):
    def __init__(self,response,lease,renew,cancel):
        super().__init__(response,response.url,response.headers,response.status,response.reason,response.extensions)
        self.lease=lease; self.renew=renew; self.cancel=cancel

    def read(self,amt=None):
        if self.closed: return b''
        try:
            self.cancel.raise_if_cancelled()
            self.renew()
            # Call original directly: Response.read wraps cancellation as TransportError.
            data=self.fp.read(amt)
            self.cancel.raise_if_cancelled()
            if not data or amt is None or self.fp.closed: self.close()
            return data
        except BaseException:
            self.close(); self.cancel.raise_if_cancelled(); raise

    def close(self):
        try: super().close()
        finally:
            lease=getattr(self,'lease',None)
            if lease is not None:
                self.lease=None; lease.__exit__(None,None,None)


class InstagramDownloader(_CancellableDownloader):
    def __init__(self,options,context,kind):
        if context.instagram_rate is None:
            from clipflow.providers.base import MediaFailure
            raise MediaFailure('instagram_rate_policy_required')
        self.instagram_context=context; self.instagram_kind=kind; self._responses=[]
        super().__init__(options,context.cancel)

    def build_request_director(self,handlers,preferences=None):
        # The default requests/curl clients follow redirects below urlopen.
        # Keep a scoped urllib handler so those additional HTTP requests also
        # consult the shared budget. No global registry or library patch.
        context=self.instagram_context
        owner=self
        class PacedRedirect(RedirectHandler):
            handler_order=499
            def redirect_request(self,req,fp,code,msg,headers,newurl):
                try:
                    context.instagram_rate.acquire('cdn' if owner.instagram_kind=='cdn' else 'metadata',context.cancel)
                    return super().redirect_request(req,fp,code,msg,headers,newurl)
                except InstagramDeferred as error:
                    fp.close(); context.emit(error.decision); raise
                except BaseException:
                    fp.close(); raise
        class PacedUrllibRH(UrllibRH):
            def _send(self,request):
                try: return super()._send(request)
                except WorkCancelled as error: raise _CancelledRequest(error) from None
            def _create_instance(self,*args,**kwargs):
                opener=super()._create_instance(*args,**kwargs)
                opener.add_handler(PacedRedirect())
                return opener
        return super().build_request_director([PacedUrllibRH])

    def urlopen(self,request):
        context=self.instagram_context
        lease=gated_request(context,self.instagram_kind)
        renew=lease.__enter__()
        if self.instagram_kind=='post': self.instagram_kind='metadata'
        try:
            response=super().urlopen(request)
        except _CancelledRequest as error:
            lease.__exit__(None,None,None)
            raise error.stopped from None
        except HTTPError as error:
            try:
                if error.status==429:
                    decision=context.instagram_rate.record_429(error.response.headers.get('Retry-After'))
                    error.close(); context.emit(decision)
                    raise InstagramDeferred(decision) from None
                error.close()
                raise
            finally: lease.__exit__(None,None,None)
        except BaseException:
            lease.__exit__(None,None,None); context.cancel.raise_if_cancelled(); raise
        wrapped=LeasedResponse(response,lease,renew,context.cancel)
        self._responses.append(wrapped)
        return wrapped

    def close(self):
        try:
            for response in self._responses: response.close()
            self._responses.clear()
        finally: super().close()
