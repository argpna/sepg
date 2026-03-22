import sys

import bencodepy
import pytest

from sepg.download.torrent import ensure_dir, fetch_to_tmp, is_url, list_torrent_files, torrent_piece_info


def test_is_url_accepts_http_and_https():
    assert is_url("http://example.com/x.torrent")
    assert is_url("https://example.com/x.torrent")


def test_is_url_rejects_local_paths():
    assert not is_url("/tmp/x.torrent")
    assert not is_url("relative/x.torrent")


def test_ensure_dir_creates_nested_directories(tmp_path):
    target = tmp_path / "a" / "b" / "c"
    result = ensure_dir(target)
    assert result == target
    assert target.is_dir()


def test_ensure_dir_is_idempotent(tmp_path):
    target = tmp_path / "a"
    target.mkdir()
    ensure_dir(target)  # must not raise even though it already exists
    assert target.is_dir()


def test_fetch_to_tmp_downloads_when_missing(tmp_path, monkeypatch):
    calls = []

    def fake_urlretrieve(url, dst):
        calls.append((url, dst))
        dst.write_bytes(b"torrent-bytes")

    monkeypatch.setattr("urllib.request.urlretrieve", fake_urlretrieve)

    url = "https://example.com/site.torrent"
    dst = fetch_to_tmp(url, tmp_path, force=False)

    assert dst == tmp_path / "site.torrent"
    assert len(calls) == 1


def test_fetch_to_tmp_uses_cache_when_present_and_not_forced(tmp_path, monkeypatch):
    cached = tmp_path / "site.torrent"
    cached.write_bytes(b"already-here")

    def fail_if_called(url, dst):
        raise AssertionError("should not re-download when cache is valid")

    monkeypatch.setattr("urllib.request.urlretrieve", fail_if_called)

    dst = fetch_to_tmp("https://example.com/site.torrent", tmp_path, force=False)

    assert dst == cached
    assert cached.read_bytes() == b"already-here"


def test_fetch_to_tmp_force_redownloads_even_if_cached(tmp_path, monkeypatch):
    cached = tmp_path / "site.torrent"
    cached.write_bytes(b"stale")
    calls = []

    def fake_urlretrieve(url, dst):
        calls.append(url)
        cached.write_bytes(b"fresh")

    monkeypatch.setattr("urllib.request.urlretrieve", fake_urlretrieve)

    fetch_to_tmp("https://example.com/site.torrent", tmp_path, force=True)

    assert len(calls) == 1
    assert cached.read_bytes() == b"fresh"


def test_fetch_to_tmp_redownloads_empty_cached_file(tmp_path, monkeypatch):
    cached = tmp_path / "site.torrent"
    cached.write_bytes(b"")
    calls = []

    def fake_urlretrieve(url, dst):
        calls.append(url)
        cached.write_bytes(b"fresh")

    monkeypatch.setattr("urllib.request.urlretrieve", fake_urlretrieve)

    fetch_to_tmp("https://example.com/site.torrent", tmp_path, force=False)

    assert len(calls) == 1


def test_list_torrent_files_single_file_torrent(tmp_path):
    data = {b"info": {b"name": b"vi.stackexchange.com.7z", b"length": 12345}}
    torrent_path = tmp_path / "single.torrent"
    torrent_path.write_bytes(bencodepy.encode(data))

    files = list_torrent_files(torrent_path)

    assert files == [("vi.stackexchange.com.7z", 12345)]


def test_list_torrent_files_multi_file_torrent(tmp_path):
    data = {
        b"info": {
            b"name": b"stackexchange",
            b"files": [
                {b"length": 111, b"path": [b"vi.stackexchange.com.7z"]},
                {b"length": 222, b"path": [b"nested", b"Posts.xml.7z"]},
            ],
        }
    }
    torrent_path = tmp_path / "multi.torrent"
    torrent_path.write_bytes(bencodepy.encode(data))

    files = list_torrent_files(torrent_path)

    assert files == [
        ("stackexchange/vi.stackexchange.com.7z", 111),
        ("stackexchange/nested/Posts.xml.7z", 222),
    ]


def test_list_torrent_files_raises_systemexit_when_bencodepy_missing(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "bencodepy", None)
    torrent_path = tmp_path / "x.torrent"
    torrent_path.write_bytes(b"whatever")

    with pytest.raises(SystemExit, match="bencodepy is required"):
        list_torrent_files(torrent_path)


def test_torrent_piece_info_single_file_torrent(tmp_path):
    data = {
        b"info": {
            b"name": b"vi.stackexchange.com.7z",
            b"length": 100,
            b"piece length": 16,
            b"pieces": b"x" * 40,  # two 20-byte digests
        }
    }
    torrent_path = tmp_path / "single.torrent"
    torrent_path.write_bytes(bencodepy.encode(data))

    piece_length, pieces, entries = torrent_piece_info(torrent_path)

    assert piece_length == 16
    assert pieces == b"x" * 40
    assert entries == [("vi.stackexchange.com.7z", 0, 100)]


def test_torrent_piece_info_multi_file_torrent_computes_cumulative_offsets(tmp_path):
    data = {
        b"info": {
            b"name": b"stackexchange",
            b"piece length": 16,
            b"pieces": b"x" * 20,
            b"files": [
                {b"length": 111, b"path": [b"vi.stackexchange.com.7z"]},
                {b"length": 222, b"path": [b"nested", b"Posts.xml.7z"]},
            ],
        }
    }
    torrent_path = tmp_path / "multi.torrent"
    torrent_path.write_bytes(bencodepy.encode(data))

    _piece_length, _pieces, entries = torrent_piece_info(torrent_path)

    assert entries == [
        ("stackexchange/vi.stackexchange.com.7z", 0, 111),
        ("stackexchange/nested/Posts.xml.7z", 111, 222),
    ]
