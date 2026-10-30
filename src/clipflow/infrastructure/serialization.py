"""Strict, credential-free option snapshots shared by queue and settings codecs."""

import re
from dataclasses import asdict
from pathlib import Path

from clipflow.domain.models import DownloadOptions


def reference(value):
    if value is not None and (
        not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', value)
    ):
        raise ValueError('invalid_profile_reference')
    return value


def path_value(value):
    if not isinstance(value, str) or not value or '\0' in value:
        raise ValueError('invalid_path')
    return Path(value)


def encode_options(options):
    raw = asdict(options)
    raw['folder'] = str(options.folder)
    decode_options(raw)
    return raw


def decode_options(raw):
    if not isinstance(raw, dict):
        raise ValueError('invalid_options')
    fields = {
        'folder',
        'format',
        'max_height',
        'media_filter',
        'author_folder',
        'post_folder',
        'description',
        'auth_profile',
    }
    # numbering arrived in 2.0.3; snapshots written before it stay readable.
    if set(raw) - {'numbering'} != fields:
        raise ValueError('invalid_options')
    if any(
        type(raw[key]) is not bool
        for key in ('author_folder', 'post_folder', 'numbering')
        if key in raw
    ):
        raise ValueError('invalid_boolean')
    reference(raw['auth_profile'])
    return DownloadOptions(**dict(raw, folder=path_value(raw['folder'])))
