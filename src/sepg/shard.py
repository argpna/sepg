import csv
import html
import multiprocessing as mp
import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from .log import step, warn
from .manifest import Manifest, ManifestPart
from .schema import Schema


def _decode_xml_attr(raw: bytes) -> str:
    if b"&" in raw:
        return html.unescape(raw.decode("utf-8", errors="strict"))
    return raw.decode("utf-8", errors="strict")


def _open_new_part_file(
    out_dir: Path,
    shard_id: int,
    part_id: int,
    header_columns: list[str],
    *,
    file_buffer_bytes: int,
) -> tuple[Path, TextIO, csv.writer]:
    out_dir.mkdir(parents=True, exist_ok=True)
    part_path = out_dir / f"shard-{shard_id:02d}-{part_id:06d}.csv"
    part_file = open(part_path, "w", encoding="utf-8", newline="", buffering=file_buffer_bytes)
    writer = csv.writer(part_file, lineterminator="\n")
    writer.writerow(header_columns)
    return part_path, part_file, writer


def _iter_xml_row_range(
    xml_path: Path,
    *,
    start: int,
    end: int,
    xml_cols: list[str],
) -> Iterable[list[str | None]]:
    """Yield one row (as a list aligned to xml_cols) per `<row .../>` line in [start, end).

    Hand-rolled byte scanner, for throughput on multi-GB dumps. Supported input: SE dump style,
    where each `<row .../>` is self-closing and entirely on one line. A dump that wraps a
    `<row>`'s attributes across lines violates this assumption and will silently produce
    truncated/wrong rows rather than raising - a deliberate trade-off."""

    col_index: dict[bytes, int] = {col.encode("utf-8"): i for i, col in enumerate(xml_cols)}
    row_len = len(xml_cols)

    row_tag_lines = 0
    yielded = 0

    with xml_path.open("rb") as f:
        f.seek(start)
        if start != 0:
            f.readline()

        while True:
            line_start = f.tell()
            if line_start >= end:
                break

            line = f.readline()
            if not line:
                break

            if b"<row" not in line:
                continue

            row_tag_lines += 1
            row: list[str | None] = [None] * row_len

            row_tag = line.find(b"<row")
            if row_tag < 0:
                continue
            i = line.find(b" ", row_tag)
            if i < 0:
                # no attributes on the "<row" line itself - the one-row-per-line contract this
                # parser depends on doesn't hold for this row, so skip it rather than guess.
                continue

            n = len(line)

            while i < n:
                ch = line[i]
                if ch <= 32:
                    i += 1
                    continue
                if ch == ord(b"/") or ch == ord(b">"):
                    break

                name_start = i
                eq = line.find(b"=", name_start)
                if eq < 0:
                    break

                name = line[name_start:eq].strip()
                i = eq + 1
                if i >= n:
                    break

                if line[i] != ord(b'"'):
                    q1 = line.find(b'"', i)
                    if q1 < 0:
                        break
                    i = q1

                i += 1
                if i >= n:
                    break

                val_start = i
                q2 = line.find(b'"', val_start)
                if q2 < 0:
                    break

                raw_val = line[val_start:q2]
                i = q2 + 1

                col_idx = col_index.get(name)
                if col_idx is not None:
                    row[col_idx] = _decode_xml_attr(raw_val)

            yielded += 1
            yield row

    if row_tag_lines != yielded:
        warn(
            f"{xml_path.name} [{start}:{end}]: found {row_tag_lines} '<row' line(s) but only "
            f"parsed {yielded} - a <row> likely spans multiple lines, violating the "
            "one-row-per-line assumption this parser depends on; some rows were silently skipped"
        )


@dataclass
class ShardConfig:
    shards: int = 8
    shard_workers: int = 1
    max_rows_per_part: int = 5_000_000
    file_buffer_bytes: int = 1024 * 1024
    part_stride: int = 10_000


def _shard_worker(job: dict) -> dict:
    worker_id: int = job["worker_id"]
    xml_path: Path = job["xml_path"]
    start: int = job["start"]
    end: int = job["end"]
    out_dir: Path = job["out_dir"]
    xml_cols: list[str] = job["xml_cols"]
    pg_cols: list[str] = job["pg_cols"]
    pk_idx: int | None = job["pk_idx"]
    cfg: ShardConfig = job["cfg"]

    if pk_idx is None:
        raise RuntimeError("Schema primary key missing")

    shard_writers: list[tuple[Path, TextIO, csv.writer]] = []
    rows_curr_part = [0] * cfg.shards
    part_seq = [0] * cfg.shards

    created_parts: list[dict] = []
    total_rows = 0

    def record_part(part_path: Path, part_rows: int) -> None:
        if part_rows == 0:
            try:
                part_path.unlink(missing_ok=True)
            except OSError as e:
                warn(f"[shard] failed to delete empty part {part_path}: {e}")
            return
        rel = part_path.relative_to(out_dir).as_posix()
        size_bytes = part_path.stat().st_size if part_path.exists() else 0
        created_parts.append(
            {
                "path": rel,
                "rows": int(part_rows),
                "bytes": int(size_bytes),
                "status": "created",
            }
        )

    for shard_id in range(cfg.shards):
        part_seq[shard_id] = 1
        part_id = worker_id * cfg.part_stride + part_seq[shard_id]
        part_path, part_file, writer = _open_new_part_file(
            out_dir,
            shard_id,
            part_id,
            pg_cols,
            file_buffer_bytes=cfg.file_buffer_bytes,
        )
        shard_writers.append((part_path, part_file, writer))
        rows_curr_part[shard_id] = 0

    shard_count = int(cfg.shards)
    max_rows_per_part = int(cfg.max_rows_per_part)

    for row in _iter_xml_row_range(xml_path, start=start, end=end, xml_cols=xml_cols):
        total_rows += 1

        pk_val = row[pk_idx]
        if pk_val is None or pk_val == "":
            raise RuntimeError(f"worker={worker_id} missing primary key value")

        try:
            shard_id = int(pk_val) % shard_count
        except ValueError as e:
            raise RuntimeError(f"worker={worker_id} invalid primary key: {pk_val!r}") from e

        part_path, part_file, writer = shard_writers[shard_id]
        writer.writerow(["" if val is None else val for val in row])
        rows_curr_part[shard_id] += 1

        if rows_curr_part[shard_id] >= max_rows_per_part:
            try:
                part_file.flush()
                part_file.close()
            except OSError as e:
                warn(f"failed to close part file {part_path}: {e}")

            record_part(part_path, rows_curr_part[shard_id])

            part_seq[shard_id] += 1
            part_id = worker_id * cfg.part_stride + part_seq[shard_id]
            part_path, part_file, writer = _open_new_part_file(
                out_dir,
                shard_id,
                part_id,
                pg_cols,
                file_buffer_bytes=cfg.file_buffer_bytes,
            )
            shard_writers[shard_id] = (part_path, part_file, writer)
            rows_curr_part[shard_id] = 0

    for shard_id in range(cfg.shards):
        part_path, part_file, _writer = shard_writers[shard_id]
        try:
            part_file.flush()
            part_file.close()
        except OSError as e:
            warn(f"failed to close part file {part_path}: {e}")
        record_part(part_path, rows_curr_part[shard_id])

    return {"rows": int(total_rows), "parts": created_parts}


def shard_xml(
    *,
    xml_path: Path,
    schema_dir: Path,
    out_dir: Path,
    cfg: ShardConfig,
) -> Path:

    schema = Schema.from_dir(schema_dir)

    xml_cols = schema.xml_columns
    xml_pk = schema.xml_primary_key
    pg_cols = schema.pg_columns

    pk_idx: int | None = None
    if xml_pk:
        try:
            pk_idx = xml_cols.index(xml_pk)
        except ValueError:
            pk_idx = None

    out_dir.mkdir(parents=True, exist_ok=True)

    xml_size = os.path.getsize(xml_path)

    worker_count = int(cfg.shard_workers)
    if worker_count <= 0:
        worker_count = 1

    min_chunk = 64 * 1024 * 1024
    cap = max(1, xml_size // min_chunk) if xml_size > 0 else 1
    worker_count = max(1, min(worker_count, cap))

    chunk_size = xml_size // worker_count if worker_count else xml_size
    byte_ranges: list[tuple[int, int]] = []
    for i in range(worker_count):
        start = i * chunk_size
        end = xml_size if i == worker_count - 1 else (i + 1) * chunk_size
        byte_ranges.append((start, end))

    jobs = [
        dict(
            worker_id=wid,
            xml_path=xml_path,
            start=start,
            end=end,
            out_dir=out_dir,
            xml_cols=xml_cols,
            pg_cols=pg_cols,
            pk_idx=pk_idx,
            cfg=cfg,
        )
        for wid, (start, end) in enumerate(byte_ranges)
    ]

    if worker_count == 1:
        results = [_shard_worker(jobs[0])]
    else:
        try:
            ctx = mp.get_context("fork")
        except ValueError:
            ctx = mp.get_context("spawn")
        with ctx.Pool(processes=worker_count) as pool:
            results = pool.map(_shard_worker, jobs, chunksize=1)

    manifest = Manifest(
        table=schema.pg_table,
        primary_key=schema.pg_primary_key,
        columns=pg_cols,
        source_xml=str(xml_path),
        shards=int(cfg.shards),
        parts=[],
        total_rows=0,
        schema_version=3,
    )

    total_rows = 0
    parts: list[ManifestPart] = []
    for r in results:
        total_rows += int(r["rows"])
        for p in r["parts"]:
            parts.append(
                ManifestPart(
                    path=str(p["path"]),
                    rows=int(p["rows"]),
                    bytes=int(p["bytes"]),
                    status=str(p["status"]),
                )
            )

    parts.sort(key=lambda x: x.path)
    manifest.parts = parts
    manifest.total_rows = int(total_rows)

    manifest_path = out_dir / "manifest.json"
    manifest.write(manifest_path)

    step(
        "ok",
        f"{schema.pg_table}: rows={total_rows:,}, "
        f"shards={cfg.shards}, shard_workers={worker_count}, "
        f"manifest={manifest_path}",
    )

    return manifest_path
