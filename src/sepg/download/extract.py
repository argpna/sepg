from pathlib import Path


def _check_members_stay_under(names: list[str], extract_dir: Path) -> None:
    """Reject archive member names that would escape extract_dir once joined and resolved i.e
    `../` traversal, or an absolute path baked into the archive. py7zr is generally well-behaved,
    but archives are fetched from a torrent swarm so validate before calling extractall() rather
    than trust the library."""

    for name in names:
        target = (extract_dir / name).resolve()
        if target != extract_dir and extract_dir not in target.parents:
            raise SystemExit(f"refusing to extract: member path escapes extract dir: {name!r}")


def extract_7z(archive: Path, extract_dir: Path) -> None:
    try:
        import py7zr
    except ImportError as e:
        raise SystemExit("py7zr is required for --extract") from e

    extract_dir.mkdir(parents=True, exist_ok=True)
    resolved_extract_dir = extract_dir.resolve()

    print(f"[extract] {archive} -> {extract_dir}")
    with py7zr.SevenZipFile(str(archive), mode="r") as zf:
        _check_members_stay_under(zf.getnames(), resolved_extract_dir)
        zf.extractall(path=str(extract_dir))
