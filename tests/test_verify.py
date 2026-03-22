import hashlib

from sepg.download.verify import verify_piece_hashes


def _files(*lengths):
    return [{"name": f"file{i}.7z", "length": n} for i, n in enumerate(lengths)]


def _piece_hashes(*chunks: bytes) -> bytes:
    return b"".join(hashlib.sha1(c).digest() for c in chunks)


def test_verify_piece_hashes_passes_for_matching_content(tmp_path):
    files = _files(16)
    (tmp_path / "file0.7z").write_bytes(b"AAAAAAAABBBBBBBB")
    pieces = _piece_hashes(b"AAAAAAAA", b"BBBBBBBB")
    entries = [("file0.7z", 0, 16)]

    assert verify_piece_hashes(tmp_path, files, [0], piece_length=8, pieces=pieces, torrent_entries=entries) == []


def test_verify_piece_hashes_flags_corrupted_piece(tmp_path):
    files = _files(16)
    (tmp_path / "file0.7z").write_bytes(b"AAAAAAAAxxxxxxxx")  # second piece corrupted
    pieces = _piece_hashes(b"AAAAAAAA", b"BBBBBBBB")
    entries = [("file0.7z", 0, 16)]

    mismatches = verify_piece_hashes(tmp_path, files, [0], piece_length=8, pieces=pieces, torrent_entries=entries)

    assert len(mismatches) == 1
    assert "piece(s) [1]" in mismatches[0]


def test_verify_piece_hashes_flags_missing_file(tmp_path):
    files = _files(16)
    pieces = _piece_hashes(b"AAAAAAAA", b"BBBBBBBB")
    entries = [("file0.7z", 0, 16)]

    mismatches = verify_piece_hashes(tmp_path, files, [0], piece_length=8, pieces=pieces, torrent_entries=entries)

    assert mismatches == ["file0.7z: missing on disk"]


def test_verify_piece_hashes_skips_trailing_partial_piece(tmp_path):
    # file is 20 bytes with piece_length=8: piece 0 and 1 are fully covered (bytes 0-15),
    # the last 4 bytes (16-19) are a trailing partial piece and should not be checked at all
    # corrupting only those bytes must not be reported.
    files = _files(20)
    (tmp_path / "file0.7z").write_bytes(b"AAAAAAAABBBBBBBBzzzz")
    pieces = _piece_hashes(b"AAAAAAAA", b"BBBBBBBB")
    entries = [("file0.7z", 0, 20)]

    assert verify_piece_hashes(tmp_path, files, [0], piece_length=8, pieces=pieces, torrent_entries=entries) == []


def test_verify_piece_hashes_skips_files_not_in_torrent_entries(tmp_path):
    files = _files(16)
    (tmp_path / "file0.7z").write_bytes(b"AAAAAAAABBBBBBBB")

    assert verify_piece_hashes(tmp_path, files, [0], piece_length=8, pieces=b"", torrent_entries=[]) == []
