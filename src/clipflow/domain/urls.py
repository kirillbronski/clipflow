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
            return ParsedLink(Service.YOUTUBE, kind, identity, f'https://www.youtube.com/{route}?{key}={identity}')
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
        if host == 'getcourse.ru' or host.endswith(('.getcourse.ru', '.getcourse.io')):
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


def request_key(request: DownloadRequest) -> str:
    options = asdict(request.options)
    options['folder'] = os.path.normcase(str(request.options.folder))
    data = {'service': request.link.service, 'kind': request.link.kind,
            'id': request.link.canonical_id, 'options': options,
            'selection': sorted(request.selection) if request.selection is not None else None,
            'profile_limit': request.profile_limit}
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
