import argparse
import hashlib
from pathlib import Path

import bencodepy
import pytest

import sepg.download.core as core


class _FakeRPC:
    def __init__(self, url):
        self.url = url
        self.calls = []

    def call(self, method, arguments=None):
        self.calls.append((method, arguments))
        return {"result": "success"}


def _args(**overrides):
    defaults = dict(
        torrent="local.torrent",
        out_dir=None,
        extract_dir=None,
        filter=None,
        list_files=False,
        extract=False,
        rm_archives=False,
        keep_torrent=False,
        verify_hashes=False,
        rpc_url="http://transmission:9091/transmission/rpc",
        tmp_dir=None,
        force_torrent=False,
        poll=0.0,
        wait_seconds=5,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def test_list_files_mode_prints_matching_files_and_excludes_padding(tmp_path, monkeypatch, capsys):
    torrent_path = tmp_path / "local.torrent"
    torrent_path.write_bytes(b"fake")

    monkeypatch.setattr(
        core,
        "list_torrent_files",
        lambda p: [
            ("site/Posts.xml.7z", 100),
            ("site/Badges.xml.7z", 50),
            ("site/.____padding_file/0", 10),
        ],
    )

    args = _args(torrent=str(torrent_path), list_files=True, filter="*Posts*")
    core.run_downloader(args)

    out = capsys.readouterr().out
    assert "Posts.xml.7z (100 bytes)" in out
    assert "Badges.xml.7z" not in out
    assert "padding_file" not in out


def test_out_dir_required_unless_list_files():
    args = _args(out_dir=None, list_files=False)
    with pytest.raises(SystemExit, match="--out-dir is required"):
        core.run_downloader(args)


def test_out_dir_must_be_absolute():
    args = _args(out_dir=Path("relative/dir"), list_files=False)
    with pytest.raises(SystemExit, match="must be an absolute path"):
        core.run_downloader(args)


def test_raises_when_torrent_file_not_found(tmp_path):
    missing = tmp_path / "missing.torrent"
    args = _args(torrent=str(missing), out_dir=tmp_path / "out", list_files=False)
    with pytest.raises(SystemExit, match="Torrent not found"):
        core.run_downloader(args)


def test_raises_when_no_files_match_filter(tmp_path, monkeypatch):
    torrent_path = tmp_path / "local.torrent"
    torrent_path.write_bytes(b"fake")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    monkeypatch.setattr(core, "TransmissionRPC", lambda url: object())
    monkeypatch.setattr(core, "add_torrent", lambda rpc, torrent_bytes, out_dir: {"id": 1})
    monkeypatch.setattr(
        core,
        "torrent_get",
        lambda rpc, tid: {"files": [{"name": "site/Posts.xml.7z"}]},
    )

    args = _args(torrent=str(torrent_path), out_dir=out_dir, filter="*nomatch*")
    with pytest.raises(SystemExit, match="No files matched --filter"):
        core.run_downloader(args)


def test_raises_on_download_timeout(tmp_path, monkeypatch):
    torrent_path = tmp_path / "local.torrent"
    torrent_path.write_bytes(b"fake")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    files = [{"name": "site/Posts.xml.7z", "length": 100}]

    monkeypatch.setattr(core, "TransmissionRPC", _FakeRPC)
    monkeypatch.setattr(core, "add_torrent", lambda rpc, torrent_bytes, out_dir: {"id": 1})
    monkeypatch.setattr(core, "apply_selection", lambda rpc, tid, total, wanted: None)
    monkeypatch.setattr(
        core,
        "torrent_get",
        lambda rpc, tid: {
            "downloadDir": str(out_dir),
            "files": files,
            "fileStats": [{"bytesCompleted": 0}],
            "percentDone": 0.0,
            "rateDownload": 0,
        },
    )

    args = _args(torrent=str(torrent_path), out_dir=out_dir, wait_seconds=-1, poll=0)
    with pytest.raises(SystemExit, match="Download timed out"):
        core.run_downloader(args)


def test_successful_download_extracts_and_removes_torrent(tmp_path, monkeypatch):
    torrent_path = tmp_path / "local.torrent"
    torrent_path.write_bytes(b"fake")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    archive = out_dir / "Posts.xml.7z"
    archive.write_bytes(b"x" * 10)

    files = [{"name": "Posts.xml.7z", "length": 10}]
    extract_calls = []
    rpcs: list[_FakeRPC] = []

    def make_rpc(url):
        rpc = _FakeRPC(url)
        rpcs.append(rpc)
        return rpc

    monkeypatch.setattr(core, "TransmissionRPC", make_rpc)
    monkeypatch.setattr(core, "add_torrent", lambda rpc, torrent_bytes, out_dir: {"id": 42})
    monkeypatch.setattr(core, "apply_selection", lambda rpc, tid, total, wanted: None)
    monkeypatch.setattr(
        core,
        "torrent_get",
        lambda rpc, tid: {
            "downloadDir": str(out_dir),
            "files": files,
            "fileStats": [{"bytesCompleted": 10}],
            "percentDone": 1.0,
            "rateDownload": 0,
        },
    )
    monkeypatch.setattr(core, "extract_7z", lambda path, dest: extract_calls.append((path, dest)))

    args = _args(torrent=str(torrent_path), out_dir=out_dir, extract=True, wait_seconds=5, poll=0)
    core.run_downloader(args)

    assert extract_calls == [(archive, out_dir)]
    assert ("torrent-start", {"ids": [42]}) in rpcs[0].calls
    assert ("torrent-remove", {"ids": [42], "delete-local-data": False}) in rpcs[0].calls


def test_keep_torrent_skips_removal(tmp_path, monkeypatch):
    torrent_path = tmp_path / "local.torrent"
    torrent_path.write_bytes(b"fake")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "Posts.xml.7z").write_bytes(b"x" * 10)

    files = [{"name": "Posts.xml.7z", "length": 10}]
    rpcs: list[_FakeRPC] = []

    def make_rpc(url):
        rpc = _FakeRPC(url)
        rpcs.append(rpc)
        return rpc

    monkeypatch.setattr(core, "TransmissionRPC", make_rpc)
    monkeypatch.setattr(core, "add_torrent", lambda rpc, torrent_bytes, out_dir: {"id": 42})
    monkeypatch.setattr(core, "apply_selection", lambda rpc, tid, total, wanted: None)
    monkeypatch.setattr(
        core,
        "torrent_get",
        lambda rpc, tid: {
            "downloadDir": str(out_dir),
            "files": files,
            "fileStats": [{"bytesCompleted": 10}],
            "percentDone": 1.0,
            "rateDownload": 0,
        },
    )

    args = _args(torrent=str(torrent_path), out_dir=out_dir, keep_torrent=True, wait_seconds=5, poll=0)
    core.run_downloader(args)

    assert all(method != "torrent-remove" for method, _ in rpcs[0].calls)


def _write_single_file_torrent(torrent_path: Path, name: str, content: bytes, piece_length: int) -> None:
    pieces = b"".join(
        hashlib.sha1(content[i : i + piece_length]).digest() for i in range(0, len(content), piece_length)
    )
    data = {
        b"info": {
            b"name": name.encode(),
            b"length": len(content),
            b"piece length": piece_length,
            b"pieces": pieces,
        }
    }
    torrent_path.write_bytes(bencodepy.encode(data))


def test_verify_hashes_passes_for_correct_pieces(tmp_path, monkeypatch, capsys):
    torrent_path = tmp_path / "local.torrent"
    content = b"AAAAAAAABBBBBBBB"
    _write_single_file_torrent(torrent_path, "Posts.xml.7z", content, piece_length=8)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "Posts.xml.7z").write_bytes(content)

    files = [{"name": "Posts.xml.7z", "length": len(content)}]

    monkeypatch.setattr(core, "TransmissionRPC", _FakeRPC)
    monkeypatch.setattr(core, "add_torrent", lambda rpc, torrent_bytes, out_dir: {"id": 1})
    monkeypatch.setattr(core, "apply_selection", lambda rpc, tid, total, wanted: None)
    monkeypatch.setattr(
        core,
        "torrent_get",
        lambda rpc, tid: {
            "downloadDir": str(out_dir),
            "files": files,
            "fileStats": [{"bytesCompleted": len(content)}],
            "percentDone": 1.0,
            "rateDownload": 0,
        },
    )

    args = _args(torrent=str(torrent_path), out_dir=out_dir, verify_hashes=True, wait_seconds=5, poll=0)
    core.run_downloader(args)

    assert "hash verification passed" in capsys.readouterr().out


def test_verify_hashes_fails_for_corrupted_piece(tmp_path, monkeypatch):
    torrent_path = tmp_path / "local.torrent"
    content = b"AAAAAAAABBBBBBBB"
    _write_single_file_torrent(torrent_path, "Posts.xml.7z", content, piece_length=8)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "Posts.xml.7z").write_bytes(b"AAAAAAAAxxxxxxxx")  # second piece corrupted, same length

    files = [{"name": "Posts.xml.7z", "length": len(content)}]

    monkeypatch.setattr(core, "TransmissionRPC", _FakeRPC)
    monkeypatch.setattr(core, "add_torrent", lambda rpc, torrent_bytes, out_dir: {"id": 1})
    monkeypatch.setattr(core, "apply_selection", lambda rpc, tid, total, wanted: None)
    monkeypatch.setattr(
        core,
        "torrent_get",
        lambda rpc, tid: {
            "downloadDir": str(out_dir),
            "files": files,
            "fileStats": [{"bytesCompleted": len(content)}],
            "percentDone": 1.0,
            "rateDownload": 0,
        },
    )

    args = _args(torrent=str(torrent_path), out_dir=out_dir, verify_hashes=True, wait_seconds=5, poll=0)
    with pytest.raises(SystemExit, match="Piece hash verification failed"):
        core.run_downloader(args)
