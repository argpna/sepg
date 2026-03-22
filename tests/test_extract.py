import py7zr
import pytest

from sepg.download.extract import _check_members_stay_under, extract_7z


def test_check_members_stay_under_allows_nested_paths(tmp_path):
    _check_members_stay_under(["a.txt", "sub/dir/b.txt"], tmp_path)


def test_check_members_stay_under_rejects_parent_traversal(tmp_path):
    with pytest.raises(SystemExit, match="escapes extract dir"):
        _check_members_stay_under(["../../etc/passwd"], tmp_path)


def test_check_members_stay_under_rejects_absolute_path(tmp_path):
    with pytest.raises(SystemExit, match="escapes extract dir"):
        _check_members_stay_under(["/etc/passwd"], tmp_path)


def _make_archive(archive_path, files: dict[str, bytes]):
    with py7zr.SevenZipFile(archive_path, "w") as zf:
        for name, content in files.items():
            zf.writestr(content, name)


def test_extract_7z_extracts_files_to_target_dir(tmp_path):
    archive_path = tmp_path / "Posts.7z"
    _make_archive(archive_path, {"Posts.xml": b'<posts><row Id="1" /></posts>'})
    extract_dir = tmp_path / "out"

    extract_7z(archive_path, extract_dir)

    assert (extract_dir / "Posts.xml").read_bytes() == b'<posts><row Id="1" /></posts>'


def test_extract_7z_creates_extract_dir_if_missing(tmp_path):
    archive_path = tmp_path / "Posts.7z"
    _make_archive(archive_path, {"Posts.xml": b"data"})
    extract_dir = tmp_path / "nested" / "out"

    extract_7z(archive_path, extract_dir)

    assert (extract_dir / "Posts.xml").exists()


def test_extract_7z_rejects_archive_with_path_traversal_member(tmp_path, monkeypatch):
    archive_path = tmp_path / "evil.7z"
    _make_archive(archive_path, {"data.txt": b"pwned"})
    monkeypatch.setattr(py7zr.SevenZipFile, "getnames", lambda self: ["../../etc/passwd"])
    extract_dir = tmp_path / "out"

    with pytest.raises(SystemExit, match="escapes extract dir"):
        extract_7z(archive_path, extract_dir)
