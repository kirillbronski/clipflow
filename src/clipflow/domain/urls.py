"""Exact-host routing and stable content identity shared by every input path."""
from dataclasses import asdict
import hashlib
import json
import os
import re
from urllib.parse import parse_qs, parse_qsl, unquote, urlencode, urlparse

from .models import ContentKind, DownloadRequest, ParsedLink, Service


class InvalidLink(ValueError):
    """A user-supplied link is not a supported content URL."""


def parse_url(text: str) -> ParsedLink:
    try:
        parsed = urlparse(text.strip())
        host = (parsed.hostname or '').lower()
        if (parsed.scheme not in ('https', 'http') or parsed.username or parsed.password
                or parsed.port not in (None, 80, 443)):
            raise InvalidLink('Unsupported or credential-bearing URL')
        path = unquote(parsed.path)
        if any(part in ('.', '..') for part in path.split('/')):
            raise InvalidLink('Invalid URL path')
        query = parse_qs(parsed.query)
        if host == 'youtu.be' or host == 'youtube.com' or host.endswith('.youtube.com'):
            kind = ContentKind.VIDEO
            if host == 'youtu.be':
                identity = path.strip('/')
            elif path.rstrip('/') == '/watch':
                identity = query.get('v', [''])[0]
            elif re.fullmatch(r'/(?:shorts|live|embed)/[A-Za-z0-9_-]+/?', path):
                identity = path.strip('/').split('/')[1]
            elif path.rstrip('/') == '/playlist':
                identity = query.get('list', [''])[0]
                kind = ContentKind.PLAYLIST
            else:
                raise InvalidLink('Expected a YouTube video or playlist')
            if not re.fullmatch(r'[A-Za-z0-9_-]+', identity):
                raise InvalidLink('Missing content ID')
            key = 'list' if kind == ContentKind.PLAYLIST else 'v'
            route = 'playlist' if kind == ContentKind.PLAYLIST else 'watch'
            origin='music.youtube.com' if host=='music.youtube.com' else 'www.youtube.com'
            return ParsedLink(Service.YOUTUBE, kind, identity, f'https://{origin}/{route}?{key}={identity}')
        if host == 'instagram.com' or host.endswith('.instagram.com'):
            match = re.fullmatch(r'/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)/?', path)
            if match:
                identity = match.group(1)
                return ParsedLink(Service.INSTAGRAM, ContentKind.POST, identity, f'https://www.instagram.com/p/{identity}/')
            name = path.strip('/')
            reserved = {'p', 'reel', 'reels', 'tv', 'stories', 'accounts', 'explore', 'direct', 'about', 'legal', 'developer'}
            if re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.]{0,29}', name) and name.lower() not in reserved:
                name = name.lower()
                return ParsedLink(Service.INSTAGRAM, ContentKind.PROFILE, name, f'https://www.instagram.com/{name}/')
            raise InvalidLink('Expected an Instagram post or profile')
        regional_player = (re.fullmatch(r'[a-z0-9-]+\.(?:vhcdn|gceuproxy)\.com', host)
                           and path.rstrip('/') == '/sign-player' and query.get('json', [''])[0])
        if regional_player or host == 'getcourse.ru' or host.endswith(('.getcourse.ru', '.getcourse.io')):
            if not path or path == '/':
                raise InvalidLink('Expected a GetCourse lesson or player')
            parameters = sorted((key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
                                if not key.lower().startswith('utm_') and key.lower() not in {'fbclid', 'gclid'})
            suffix = '?' + urlencode(parameters) if parameters else ''
            kind = ContentKind.PLAYER if '/sign-player' in path or '/player/' in path else ContentKind.LESSON
            identity = host + path + suffix
            return ParsedLink(Service.GETCOURSE, kind, identity, 'https://' + identity)
    except (ValueError, AttributeError, TypeError) as error:
        if isinstance(error, InvalidLink):
            raise
        raise InvalidLink('Invalid URL') from error
    raise InvalidLink('Unsupported service')


def source_reference(link: ParsedLink) -> str:
    """Opaque comparison identity for a source that cannot be stored verbatim."""
    if link.service==Service.GETCOURSE and re.fullmatch(r'protected-[0-9a-f]{64}',link.canonical_id):
        return link.canonical_id
    return 'protected-'+hashlib.sha256(link.canonical_id.encode()).hexdigest()


def request_key(request: DownloadRequest) -> str:
    options = asdict(request.options)
    options['folder'] = os.path.normcase(str(request.options.folder))
    if not options['numbering']: del options['numbering']  # keep pre-2.0.3 queue keys
    data = {'service': request.link.service, 'kind': request.link.kind,
            'id': source_reference(request.link) if request.link.service==Service.GETCOURSE else request.link.canonical_id,
            'options': options,
            'selection': sorted(request.selection) if request.selection is not None else None,
            'profile_limit': request.profile_limit,
            'playlist': {'playlist_id':request.playlist.playlist_id,'index':request.playlist.index} if request.playlist is not None else None}
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
