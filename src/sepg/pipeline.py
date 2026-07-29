import json
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from .cleanup import remove_staging_dir
from .ddl import emit_ddl
from .loader import LoadConfig, PgConn, ensure_database, ensure_schema, load_manifest
from .log import step, warn
from .manifest import Manifest
from .paths import (
    ddl_dir,
    list_schema_tables,
    schema_dir,
    staging_dir,
    xml_path_for,
)
from .shard import ShardConfig, shard_xml


@dataclass(frozen=True)
class PipelineArgs:
    site: str
    tables: list[str]
    shards: int = 8
    shard_workers: int = 1
    max_rows_per_part: int = 5_000_000
    load_workers: int = 1
    truncate_first: bool = False
    force_shard: bool = False
    rm_staging: bool = False
    rm_source_xml: bool = False


def _need_atomic_reshard(
    *,
    manifest_path: Path,
    xml_path: Path,
    requested_shards: int,
    force: bool,
) -> tuple[bool, str]:
    """Decide whether to re-shard from scratch vs. reuse the existing manifest/parts on disk.
    Re-shards (returns True) on --force-shard, a missing/unreadable manifest, a shard-count
    change, or the manifest pointing at a different source XML file - i.e. whenever the existing
    parts can't be trusted to match what a fresh shard of (xml_path, requested_shards) would
    produce. Returns (need_reshard, human-readable reason) for logging."""
    if force:
        return True, "--force-shard"
    if not manifest_path.exists():
        return True, "no manifest"
    try:
        meta = Manifest.read(manifest_path)
    except (OSError, json.JSONDecodeError, KeyError, ValueError, TypeError):
        return True, "manifest unreadable"
    if int(meta.shards) != int(requested_shards):
        return True, f"shards mismatch (manifest={meta.shards} != requested={requested_shards})"
    if meta.source_xml and Path(meta.source_xml).resolve() != xml_path.resolve():
        return True, f"source_xml mismatch (manifest={meta.source_xml} != {xml_path})"
    return False, ""


def process_table(*, table: str, pargs: PipelineArgs, pconn: PgConn) -> None:
    step(table, "start")

    t_schema_dir = schema_dir() / table
    if not t_schema_dir.exists():
        warn(f"schema dir missing: {t_schema_dir}, skipping")
        return

    out_sql = ddl_dir() / f"create_{table}.sql"
    out_sql.parent.mkdir(parents=True, exist_ok=True)
    emit_ddl(t_schema_dir, out_sql)
    step("ddl", f"wrote {out_sql}")

    xml_path = xml_path_for(pargs.site, table)
    step("xml", str(xml_path))

    final_dir = staging_dir() / pargs.site / table
    manifest_path = final_dir / "manifest.json"

    need, reason = _need_atomic_reshard(
        manifest_path=manifest_path,
        xml_path=xml_path,
        requested_shards=pargs.shards,
        force=pargs.force_shard,
    )

    if need:
        if not xml_path.exists():
            raise FileNotFoundError(f"XML not found: {xml_path} (re-shard needed: {reason})")
        tmp_dir = final_dir.with_name(final_dir.name + f".tmp-{uuid.uuid4().hex[:8]}")
        step("shard", f"re-shard into {tmp_dir}")
        try:
            tmp_dir.mkdir(parents=True, exist_ok=False)

            shard_cfg = ShardConfig(
                shards=pargs.shards,
                shard_workers=pargs.shard_workers,
                max_rows_per_part=pargs.max_rows_per_part,
            )
            shard_xml(xml_path=xml_path, schema_dir=t_schema_dir, out_dir=tmp_dir, cfg=shard_cfg)

            if final_dir.exists():
                shutil.rmtree(final_dir)
            tmp_dir.rename(final_dir)
            step("shard", f"swapped {tmp_dir.name} -> {final_dir}")

            manifest_path = final_dir / "manifest.json"

        except Exception:
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir, ignore_errors=True)
            raise
    else:
        step("shard", f"using existing manifest: {manifest_path}")

    lcfg = LoadConfig(
        load_workers=pargs.load_workers,
        delimiter=",",
        truncate_first=pargs.truncate_first,
    )
    load_manifest(manifest_path=manifest_path, ddl_path=out_sql, conn=pconn, cfg=lcfg)

    if pargs.rm_staging:
        remove_staging_dir(manifest_path)
        step("rm", f"removed staging dir {manifest_path.parent}")

    if pargs.rm_source_xml and xml_path.exists():
        xml_path.unlink()
        step("rm", f"removed source xml {xml_path}")


def run_pipeline(*, pargs: PipelineArgs, pconn: PgConn) -> None:
    ensure_database(pconn)
    ensure_schema(pconn)
    for table in pargs.tables:
        process_table(table=table, pargs=pargs, pconn=pconn)
    step("all", "All requested tables processed.")


def resolve_tables(*, all_tables: bool, tables_csv: str | None) -> list[str]:
    if all_tables and tables_csv:
        raise SystemExit("Specify either --all or --tables, not both.")
    if all_tables:
        return list_schema_tables()
    if tables_csv:
        return [t.strip().lower() for t in tables_csv.split(",") if t.strip()]
    raise SystemExit("Provide --all or --tables.")
