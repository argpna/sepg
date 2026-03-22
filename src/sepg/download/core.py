import time
from pathlib import Path

from .extract import extract_7z
from .filters import compile_filter
from .torrent import fetch_to_tmp, is_url, list_torrent_files, torrent_piece_info
from .transmission import TransmissionRPC, add_torrent, apply_selection, torrent_get
from .verify import expected_paths, verify_piece_hashes


def run_downloader(args) -> None:
    out_dir = args.out_dir
    extract_dir = args.extract_dir or out_dir
    want = compile_filter(args.filter)

    if not args.list_files:
        if out_dir is None:
            raise SystemExit("--out-dir is required unless --list-files is set")
        if not out_dir.is_absolute():
            raise SystemExit("--out-dir must be an absolute path")

    if is_url(args.torrent):
        torrent_path = fetch_to_tmp(args.torrent, args.tmp_dir, args.force_torrent)
    else:
        torrent_path = Path(args.torrent)

    if not torrent_path.exists():
        raise SystemExit(f"Torrent not found: {torrent_path}")

    torrent_bytes = torrent_path.read_bytes()

    if args.list_files:
        files = [(p, sz) for (p, sz) in list_torrent_files(torrent_path) if ".____padding_file" not in p]
        for p, sz in files:
            if want(p):
                print(f"{p} ({sz} bytes)")
        return

    rpc = TransmissionRPC(args.rpc_url)
    t = add_torrent(rpc, torrent_bytes, out_dir)
    tid = int(t["id"])

    state = torrent_get(rpc, tid)
    files = state["files"]
    wanted = [i for i, f in enumerate(files) if want(f["name"]) and ".____padding_file" not in f["name"]]

    if not wanted:
        raise SystemExit("No files matched --filter")

    apply_selection(rpc, tid, len(files), wanted)
    rpc.call("torrent-start", {"ids": [tid]})

    deadline = time.time() + args.wait_seconds
    last_print = 0.0  # throttle progress printing a bit

    while True:
        state = torrent_get(rpc, tid)
        paths = expected_paths(Path(state["downloadDir"]), state["files"], wanted)

        # progress (flush so docker shows it)
        now = time.time()
        if now - last_print >= 0.25:
            pct = float(state.get("percentDone", 0.0)) * 100.0
            rate = int(state.get("rateDownload", 0))
            print(f"\r[{pct:5.1f}%] down {rate / 1024.0:0.1f} KiB/s          \r", end="", flush=True)
            last_print = now

        done = all(state["fileStats"][i]["bytesCompleted"] >= state["files"][i]["length"] for i in wanted)

        if done and all(p.exists() for p in paths if p.suffix == ".7z"):
            break

        if time.time() > deadline:
            print()  # finish the progress line
            raise SystemExit("Download timed out")

        time.sleep(args.poll)

    print("\n[OK] download complete")

    if args.verify_hashes:
        print("[verify] hash-checking downloaded files against the torrent's piece list...")
        piece_length, pieces, entries = torrent_piece_info(torrent_path)
        hash_mismatches = verify_piece_hashes(
            Path(state["downloadDir"]), state["files"], wanted, piece_length, pieces, entries
        )
        if hash_mismatches:
            raise SystemExit("Piece hash verification failed:\n" + "\n".join(hash_mismatches))
        print("[OK] hash verification passed")

    if args.extract:
        for p in paths:
            if p.suffix.lower() == ".7z":
                extract_7z(p, extract_dir)
                if args.rm_archives:
                    p.unlink(missing_ok=True)
                    print(f"[extract] removed {p}")

    if not args.keep_torrent:
        rpc.call("torrent-remove", {"ids": [tid], "delete-local-data": False})
