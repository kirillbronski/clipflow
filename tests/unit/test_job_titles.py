"""Display names are never part of a job's identity; they are bounded, plain strings."""

from dataclasses import replace

import pytest

from clipflow.domain.models import DownloadOptions, DownloadRequest, Job
from clipflow.domain.urls import parse_url, request_key


def test_label_is_display_only(tmp_path):
    plain = DownloadRequest(parse_url('https://youtu.be/dQw4w9WgXcQ'), DownloadOptions(tmp_path))
    labelled = replace(plain, label='Never Gonna Give You Up')
    assert labelled == plain
    assert request_key(labelled) == request_key(plain)


@pytest.mark.parametrize('value', [123, 'x' * 1001])
def test_invalid_display_names_are_rejected(tmp_path, value):
    request = DownloadRequest(parse_url('https://youtu.be/dQw4w9WgXcQ'), DownloadOptions(tmp_path))
    with pytest.raises(ValueError, match='Invalid display name'):
        replace(request, label=value)
    with pytest.raises(ValueError, match='Invalid display name'):
        Job('job', request, title=value)
