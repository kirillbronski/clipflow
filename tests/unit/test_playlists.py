"""Playlist files for players: an ordered .m3u8 beside the tracks."""

from pathlib import Path

from clipflow.application.playlists import M3uEntry, m3u_location, m3u_text


def test_m3u_text_order_paths_and_durations(tmp_path):
    folder = tmp_path / 'Плейлист'
    entries = [
        M3uEntry(folder / 'sub' / '02 Второй.mp3', 'Второй', None, 2),
        M3uEntry(folder / '01 Первый.mp3', 'Первый', 61.4, 1),
    ]
    assert m3u_text(entries, folder) == (
        '#EXTM3U\n#EXTINF:61,Первый\n01 Первый.mp3\n#EXTINF:-1,Второй\nsub/02 Второй.mp3\n'
    )


def test_m3u_location_is_safe_and_shared(tmp_path):
    root = tmp_path / 'downloads'
    files = [root / 'Плейлист' / 'a.mp4', root / 'Плейлист' / 'b.mp4']
    location = m3u_location('Лекции: «весна»/2026?', files, root)
    assert location.parent == root / 'Плейлист'
    assert location.suffix == '.m3u8'
    assert not set(location.name) & set('/:?')
    assert location.name.startswith('Лекции')


def test_no_location_without_a_shared_folder_inside_the_root(tmp_path):
    root = tmp_path / 'downloads'
    assert m3u_location('X', [tmp_path / 'elsewhere' / 'a.mp4'], root) is None
    assert m3u_location('X', [], root) is None
    assert m3u_location('X', [Path('/a/x.mp4'), Path('/b/y.mp4')], Path('/a')) is None
