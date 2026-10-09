"""Extend yt-dlp Instagram metadata with original photograph downloads."""
import os
import time
from pathlib import Path
from urllib.parse import urlparse
from yt_dlp.extractor.instagram import InstagramIE
from yt_dlp.networking import Request
from yt_dlp.utils import DownloadError
from media_names import short_media_title

def is_instagram_url(url):
    parsed=urlparse(url)
    host=(parsed.hostname or '').lower()
    return (parsed.scheme in ('https','http') and not parsed.username and not parsed.password
            and (host=='instagram.com' or host.endswith('.instagram.com'))
            and bool(__import__('re').match(r'^/(?:p|reel|reels|tv)/[^/]+',parsed.path)))

class ClipFlowInstagramIE(InstagramIE):
    @classmethod
    def ie_key(cls):return 'Instagram'

    def _extract_product_media(self, media):
        info=super()._extract_product_media(media)
        if not info.get('formats') and media.get('media_type') != 2 and not media.get('video_versions') and not media.get('video_dash_manifest'):
            candidates=[item for item in (media.get('image_versions2') or {}).get('candidates',[]) if item.get('url')]
            if candidates:
                image=max(candidates,key=lambda item:(item.get('width') or 0)*(item.get('height') or 0))
                ext=Path(urlparse(image['url']).path).suffix.lower().lstrip('.')
                if ext not in ('jpg','jpeg','png','webp','avif'):ext='jpg'
                info.update(_clipflow_photo=True,ext=ext,url=image['url'],width=image.get('width'),height=image.get('height'))
                # Keep raw extraction from rejecting photo-only publications.
                info['formats']=[{'url':image['url'],'ext':ext,'vcodec':'none','acodec':'none'}]
        return info

def media_title(info, index=None):
    author=info.get('channel') or info.get('uploader') or 'Instagram'
    caption=' '.join((info.get('description') or '').split())[:140]
    title=f'{author} - {caption}' if caption else info.get('title') or author
    return short_media_title(title)

def download_photo(ydl,info,folder,hook):
    path=Path(ydl.prepare_filename(info)).resolve()
    if not path.is_relative_to(Path(folder).resolve()):raise DownloadError('Invalid photo output path')
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.is_file():
        info['filepath']=str(path)
        return info
    partial=Path(str(path)+'.part')
    start=time.monotonic();downloaded=0
    request=Request(info['url'],headers={'Referer':'https://www.instagram.com/'})
    with ydl.urlopen(request) as response,partial.open('wb') as output:
        total=int(response.headers.get('Content-Length') or 0)
        while True:
            chunk=response.read(64*1024)
            if not chunk:break
            output.write(chunk);downloaded+=len(chunk)
            hook({'status':'downloading','downloaded_bytes':downloaded,'total_bytes':total,
                  'speed':downloaded/max(.01,time.monotonic()-start),'info_dict':info})
        if total and downloaded!=total:raise DownloadError('Photo download interrupted')
    # The hook checks cancellation even if the response was empty.
    hook({'status':'downloading','downloaded_bytes':downloaded,'total_bytes':downloaded or 1,'info_dict':info})
    if not downloaded:raise DownloadError('Instagram returned an empty photo')
    os.replace(partial,path)
    info['filepath']=str(path)
    return info


def save_description(info, media_paths, folder, file_format='TXT'):
    """Write the full Instagram caption next to each completed media file."""
    if file_format not in ('TXT', 'MD'):
        raise ValueError('Unsupported description format')
    description = info.get('description')
    if not isinstance(description, str) or not description.strip():
        return []
    from tempfile import NamedTemporaryFile
    root = Path(folder).resolve()
    written = []
    for value in media_paths:
        media = Path(value).resolve()
        if not media.is_relative_to(root) or not media.is_file():
            continue
        target = media.with_suffix('.md' if file_format == 'MD' else '.txt')
        temporary = None
        try:
            with NamedTemporaryFile(mode='w', encoding='utf-8' if file_format == 'MD' else 'utf-8-sig', newline='',
                                    dir=target.parent, prefix=target.name + '.',
                                    suffix='.tmp', delete=False) as output:
                temporary = Path(output.name)
                output.write(description)
            os.replace(temporary, target)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        written.append(str(target))
    return written


def author_directory(info, entries=()):
    """Use a genuine Instagram handle as one safe, cross-platform path segment."""
    import re
    from yt_dlp.utils import sanitize_filename
    for item in (info, *entries):
        handle = item.get('channel') or item.get('uploader_id')
        if isinstance(handle, str) and re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.]{0,29}', handle) and not handle.isdigit():
            # Windows device names are invalid directories even with a suffix.
            name = sanitize_filename(handle, restricted=False).rstrip('. ')
            if name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
                name = '_' + name
            return name
    # Never invent an account nickname or use an unchecked path from metadata.
    return 'Unknown author'
