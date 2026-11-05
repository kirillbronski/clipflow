"""Media details for rich rows: parsed from extractor info, junk dropped, never raising."""

from pathlib import Path

import pytest

from clipflow.domain.models import MediaDetails, Service
from clipflow.providers.details import details_from_info


def test_youtube_video_details():
    info = {
        'duration': 7218.4,
        'width': 1920,
        'height': 1080,
        'fps': 29.97,
        'uploader': 'Resonance Music Academy',
        'thumbnail': 'https://i.ytimg.com/vi/x/hq.jpg',
        'filesize_approx': 938_000_000,
    }
    details = details_from_info(info, 'video', Service.YOUTUBE)
    assert details == MediaDetails(
        7218.4,
        1920,
        1080,
        29.97,
        'Resonance Music Academy',
        'https://i.ytimg.com/vi/x/hq.jpg',
        938_000_000,
    )


def test_exact_filesize_wins_over_approximate():
    info = {'filesize': 10, 'filesize_approx': 20}
    assert details_from_info(info, 'video', Service.YOUTUBE).size_bytes == 10


def test_thumbnail_picked_from_list_near_320():
    info = {
        'thumbnails': [
            {'url': 'https://a/1.jpg', 'width': 120},
            {'url': 'https://a/2.jpg', 'width': 336},
            {'url': 'https://a/3.jpg', 'width': 1280},
        ]
    }
    assert details_from_info(info, 'video', Service.YOUTUBE).thumbnail == 'https://a/2.jpg'


def test_thumbnail_list_without_widths_takes_the_last():
    info = {'thumbnails': [{'url': 'https://a/1.jpg'}, {'url': 'https://a/2.jpg'}, 'junk']}
    assert details_from_info(info, 'video', Service.YOUTUBE).thumbnail == 'https://a/2.jpg'


def test_instagram_author_gets_at_and_photo_uses_its_image():
    info = {'uploader_id': 'someone', 'width': 1080, 'height': 1350, 'url': 'https://cdn/p.jpg'}
    details = details_from_info(info, 'photo', Service.INSTAGRAM)
    assert (details.author, details.thumbnail, details.width, details.height) == (
        '@someone',
        'https://cdn/p.jpg',
        1080,
        1350,
    )


def test_author_order_prefers_uploader():
    info = {'channel': 'Channel', 'uploader': 'Uploader', 'uploader_id': 'id'}
    assert details_from_info(info, 'video', Service.YOUTUBE).author == 'Uploader'
    info = {'uploader': '  ', 'channel': 'Channel'}
    assert details_from_info(info, 'video', Service.YOUTUBE).author == 'Channel'


@pytest.mark.parametrize('bad', ['12', -5, 0, float('nan'), float('inf'), True, None])
def test_bad_numbers_are_dropped(bad):
    info = {'duration': bad, 'width': bad, 'height': bad, 'fps': bad, 'filesize': bad}
    assert details_from_info(info, 'video', Service.YOUTUBE) is None


def test_float_sizes_are_not_dimensions():
    assert details_from_info({'width': 1920.5}, 'video', Service.YOUTUBE) is None


def test_http_thumbnail_is_dropped():
    assert details_from_info({'thumbnail': 'http://a/b.jpg'}, 'video', Service.YOUTUBE) is None


def test_author_is_collapsed_and_trimmed():
    details = details_from_info({'uploader': ' a\n b ' + '🎵' * 300}, 'video', Service.YOUTUBE)
    assert details.author.startswith('a b ')
    assert len(details.author) == 200


def test_empty_info_gives_none():
    assert details_from_info({}, 'video', Service.YOUTUBE) is None


def test_merged_formats_sum_their_parts():
    info = {
        'filesize_approx': 8_535_091,  # yt-dlp copies the audio part's size to the top
        'requested_formats': [
            {'filesize_approx': 90_000_000},
            {'filesize': 8_535_091},
        ],
    }
    assert details_from_info(info, 'video', Service.YOUTUBE).size_bytes == 98_535_091


def test_merged_formats_with_an_unknown_part_have_no_size():
    info = {
        'duration': 572.0,
        'filesize_approx': 8_535_091,
        'requested_formats': [{'format_id': '616'}, {'filesize': 8_535_091}],
    }
    assert details_from_info(info, 'video', Service.YOUTUBE).size_bytes is None


MERGED = {
    'duration': 600,
    'width': 3840,
    'height': 2160,
    'fps': 60,
    'requested_formats': [{'filesize': 1_400_000_000}, {'filesize': 9_000_000}],
}


def test_mp3_details_have_audio_size_and_no_picture():
    from clipflow.domain.models import DownloadOptions

    options = DownloadOptions(Path('/d'), format='mp3')
    details = details_from_info(MERGED, 'video', Service.YOUTUBE, options)
    assert (details.width, details.height, details.fps) == (None, None, None)
    assert details.size_bytes == 600 * 320_000 // 8  # CBR 320k


def test_height_limit_drops_what_the_limit_changes():
    from clipflow.domain.models import DownloadOptions

    limited = DownloadOptions(Path('/d'), max_height=720)
    details = details_from_info(MERGED, 'video', Service.YOUTUBE, limited)
    assert (details.height, details.fps, details.size_bytes) == (None, None, None)
    assert details.duration == 600.0
    fits = details_from_info(dict(MERGED, height=720), 'video', Service.YOUTUBE, limited)
    assert fits.height == 720


def test_photo_flag_follows_the_item():
    assert details_from_info({'width': 10}, 'photo', Service.INSTAGRAM).photo
    assert not details_from_info({'width': 10}, 'video', Service.INSTAGRAM).photo


def test_instagram_author_is_the_handle_not_the_display_name():
    info = {'uploader': 'B E A U T Y', 'author': 'beauty_for_ashes', 'channel': 'x'}
    assert details_from_info(info, 'video', Service.INSTAGRAM).author == '@beauty_for_ashes'
    info = {'uploader': 'Display Name', 'uploader_id': '2815873'}
    assert details_from_info(dict(info, duration=1), 'video', Service.INSTAGRAM).author is None


def test_absurd_numbers_never_raise():
    info = {'duration': 10**400, 'fps': 10**400, 'width': 10**400, 'thumbnail': 5}
    assert details_from_info(info, 'video', Service.YOUTUBE) is None  # dropped, not raised
