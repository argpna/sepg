import urllib.request
from pathlib import Path


def is_url(s: str) -> bool:
    return s.startswith(("http://", "https://"))


def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def fetch_to_tmp(url: str, tmp_dir: Path, force: bool) -> Path:
    ensure_dir(tmp_dir)
    dst = tmp_dir / (Path(url).name or "downloaded.torrent")
    if dst.exists() and dst.stat().st_size > 0 and not force:
        print(f"[INFO] using cached torrent {dst}")
        return dst
    print(f"[INFO] downloading torrent file {url} -> {dst}")
    urllib.request.urlretrieve(url, dst)
    return dst


def _decode_info(torrent_path: Path) -> dict:
    try:
        import bencodepy
    except ImportError as e:
        raise SystemExit("bencodepy is required to read torrent metadata") from e
    return bencodepy.decode(torrent_path.read_bytes())[b"info"]


def _iter_entries(info: dict) -> list[tuple[str, int, int]]:
    """(path, byte_offset, length) for every entry in the torrent's own file list, in the order
    they're concatenated into the piece stream per BEP3 - including any explicit padding-file
    entries the publisher inserted, since those still occupy space in that stream and shift the
    offset of every entry after them."""
    entries: list[tuple[str, int, int]] = []
    offset = 0

    if b"files" in info:
        top = info[b"name"].decode("utf-8", "replace")
        for entry in info[b"files"]:
            length = int(entry[b"length"])
            path = "/".join(part.decode("utf-8", "replace") for part in entry[b"path"])
            entries.append((f"{top}/{path}", offset, length))
            offset += length
    else:
        name = info[b"name"].decode("utf-8", "replace")
        length = int(info[b"length"])
        entries.append((name, 0, length))

    return entries


def list_torrent_files(torrent_path: Path) -> list[tuple[str, int]]:
    info = _decode_info(torrent_path)
    return [(path, length) for path, _offset, length in _iter_entries(info)]


def torrent_piece_info(torrent_path: Path) -> tuple[int, bytes, list[tuple[str, int, int]]]:
    """(piece_length, pieces, entries) needed to hash-check specific files against the torrent's
    own per-piece SHA1 list: `pieces` is the concatenated 20-byte-per-piece digest blob, `entries`
    gives each file's byte offset/length within the piece stream - see _iter_entries."""
    info = _decode_info(torrent_path)
    piece_length = int(info[b"piece length"])
    pieces = info[b"pieces"]
    return piece_length, pieces, _iter_entries(info)
