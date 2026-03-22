import hashlib
from pathlib import Path
from typing import Any


def expected_paths(download_dir: Path, files: list[dict[str, Any]], idxs: list[int]) -> list[Path]:
    out: list[Path] = []
    for i in idxs:
        if 0 <= i < len(files):
            name = files[i].get("name")
            if name:
                out.append(download_dir / name)
    return out


def verify_piece_hashes(
    download_dir: Path,
    files: list[dict[str, Any]],
    idxs: list[int],
    piece_length: int,
    pieces: bytes,
    torrent_entries: list[tuple[str, int, int]],
) -> list[str]:
    """Hash-check the wanted files' on-disk bytes against the torrent's own piece hashes (from
    torrent.torrent_piece_info), scoped to just those files - unlike Transmission's torrent-scoped
    `torrent-verify` RPC, which would also re-check unrelated files already on disk for that
    torrent. Skips a file's leading/trailing partial piece, since checking it needs bytes from a
    neighboring file or padding entry that may not be on disk.
    """
    by_name = {name: (offset, length) for name, offset, length in torrent_entries}
    mismatches: list[str] = []

    for i in idxs:
        if not (0 <= i < len(files)):
            continue
        f = files[i]
        name = f.get("name")
        if not name or name not in by_name:
            continue
        offset, length = by_name[name]
        path = download_dir / name
        if not path.exists():
            mismatches.append(f"{name}: missing on disk")
            continue

        first_piece = -(-offset // piece_length)  # ceil: smallest piece fully at/after offset
        end_piece = (offset + length) // piece_length  # floor: exclusive end of fully-covered pieces

        bad_pieces: list[int] = []
        with path.open("rb") as fh:
            for piece_idx in range(first_piece, end_piece):
                fh.seek(piece_idx * piece_length - offset)
                chunk = fh.read(piece_length)
                expected = pieces[piece_idx * 20 : piece_idx * 20 + 20]
                if hashlib.sha1(chunk).digest() != expected:
                    bad_pieces.append(piece_idx)

        if bad_pieces:
            mismatches.append(f"{name}: hash mismatch on piece(s) {bad_pieces}")

    return mismatches
