"""Consistent human-readable media titles and bounded filenames."""
import re

MAX_TITLE_LENGTH = 56

def short_media_title(title, limit=MAX_TITLE_LENGTH):
    title = re.sub(r'\s+', ' ', str(title or '').translate(str.maketrans({'—':'-', '–':'-', '−':'-'}))).strip()
    return title[:limit].rstrip()
