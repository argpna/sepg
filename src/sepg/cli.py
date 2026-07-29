import argparse
import os
from pathlib import Path

from .cleanup import remove_staging_dir
from .ddl import emit_ddl
from .download.core import run_downloader
from .loader import LoadConfig, PgConn, ensure_database, ensure_schema, load_manifest
from .log import step
from .paths import ddl_dir as default_ddl_root
from .paths import schema_dir as default_schema_root
from .paths import staging_dir as default_staging_root
from .pipeline import PipelineArgs, resolve_tables, run_pipeline
from .shard import ShardConfig, shard_xml


def positive_int(value: str) -> int:
    """argparse `type=` for worker/shard-count flags: rejects non-int and <= 0 values at parse
    time with a clear usage error, instead of them surfacing later as a ZeroDivisionError or a
    silently-degenerate worker count deep inside a subprocess."""
    try:
        parsed = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid int value: {value!r}") from None
    if parsed <= 0:
        raise argparse.ArgumentTypeError(f"must be a positive integer, got: {parsed}")
    return parsed


def _add_pg_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", default="localhost", help="Postgres host")
    parser.add_argument("--port", type=int, default=5432, help="Postgres port")
    parser.add_argument("--user", default="se", help="Postgres user")
    parser.add_argument("--password", default="sepass", help="Postgres password")
    parser.add_argument("--database", default="se", help="Target database")
    parser.add_argument("--schema", default="public", help="Postgres schema")


def _pg_conn(args: argparse.Namespace) -> PgConn:
    return PgConn(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.database,
        schema=args.schema,
    )


def cmd_download(args: argparse.Namespace) -> None:
    run_downloader(args)


def cmd_pipeline(args: argparse.Namespace) -> None:
    tables = resolve_tables(all_tables=args.all, tables_csv=args.tables)
    pargs = PipelineArgs(
        site=args.site,
        tables=tables,
        shards=args.shards,
        shard_workers=args.shard_workers,
        max_rows_per_part=args.max_rows_per_part,
        load_workers=args.load_workers,
        truncate_first=args.truncate_first,
        force_shard=args.force_shard,
        rm_staging=args.rm_staging,
        rm_source_xml=args.rm_source_xml,
    )
    run_pipeline(pargs=pargs, pconn=_pg_conn(args))


def cmd_shard(args: argparse.Namespace) -> None:
    table = args.xml.stem.strip().lower()
    schema_dir = args.schema_dir or (default_schema_root() / table)

    if args.out_dir:
        out_dir = args.out_dir
    else:
        if not args.site:
            raise SystemExit("--out-dir is required unless you provide --site")
        out_dir = default_staging_root() / args.site / table

    cfg = ShardConfig(
        shards=args.shards,
        shard_workers=args.shard_workers,
        max_rows_per_part=args.max_rows_per_part,
    )
    shard_xml(xml_path=args.xml, schema_dir=schema_dir, out_dir=out_dir, cfg=cfg)


def cmd_load(args: argparse.Namespace) -> None:
    conn = _pg_conn(args)
    cfg = LoadConfig(
        load_workers=args.load_workers,
        delimiter=args.delimiter,
        truncate_first=args.truncate_first,
    )
    ensure_database(conn)
    ensure_schema(conn)
    load_manifest(manifest_path=args.manifest, ddl_path=args.ddl, conn=conn, cfg=cfg)

    if args.rm_staging:
        remove_staging_dir(args.manifest)
        step("rm", f"removed staging dir {args.manifest.parent}")


def cmd_ddl(args: argparse.Namespace) -> None:
    if args.table:
        table = args.table.strip().lower()
        schema_dir = args.schema_dir or (default_schema_root() / table)
        out_sql = args.out_sql or (default_ddl_root() / f"create_{table}.sql")
    else:
        if args.schema_dir is None or args.out_sql is None:
            raise SystemExit("Provide --table, or provide both --schema-dir and --out-sql")
        schema_dir = args.schema_dir
        out_sql = args.out_sql

    out = emit_ddl(schema_dir, out_sql)
    print(f"[ddl] wrote {out}")


def _add_download_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "download",
        help="Download a torrent via Transmission and optionally extract 7z archives",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--torrent", required=True, help="Torrent URL or local .torrent file")
    p.add_argument("--out-dir", type=Path, default=None, help="Download destination (required unless --list-files)")
    p.add_argument("--filter", default="", help="File filter, substring match or re:<regex>")

    p.add_argument("--list-files", action="store_true", help="List matching files and exit")
    p.add_argument("--extract", action="store_true", help="Extract .7z archives after download")
    p.add_argument("--extract-dir", type=Path, help="Extraction destination (defaults to --out-dir)")
    p.add_argument("--rm-archives", action="store_true", help="Delete .7z files after extraction")
    p.add_argument("--keep-torrent", action="store_true", help="Keep torrent in Transmission after finish")
    p.add_argument(
        "--verify-hashes",
        action="store_true",
        help="After download, hash-check wanted files against the torrent's own piece list",
    )

    p.add_argument("--rpc-url", default="http://transmission:9091/transmission/rpc", help="Transmission RPC URL")
    p.add_argument("--tmp-dir", type=Path, default=Path("/tmp"), help="Temp dir for .torrent file cache")
    p.add_argument("--force-torrent", action="store_true", help="Re-download .torrent file even if cached")
    p.add_argument("--poll", type=float, default=1.0, help="Progress poll interval in seconds")
    p.add_argument("--wait-seconds", type=int, default=604800, help="Download timeout in seconds")
    p.set_defaults(func=cmd_download)


def _add_pipeline_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "pipeline",
        help="Run the full pipeline: shard XML to CSV, then load into Postgres",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--site", required=True, help="StackExchange site name")
    _add_pg_args(p)
    p.add_argument("--tables", help="Comma-separated list, e.g. badges,comments,posts")
    p.add_argument("--all", action="store_true", help="All tables")
    p.add_argument("--shards", type=positive_int, default=8, help="Number of output shards")
    p.add_argument("--shard-workers", type=positive_int, default=1, help="Parallel XML shard workers")
    p.add_argument("--max-rows-per-part", type=int, default=5_000_000, help="Rows per CSV part file")
    p.add_argument(
        "--load-workers", type=positive_int, default=max(1, os.cpu_count() or 1), help="Parallel COPY workers"
    )
    p.add_argument("--truncate-first", action="store_true", help="Truncate table before loading")
    p.add_argument("--force-shard", action="store_true", help="Force re-shard even if manifest exists")
    p.add_argument("--rm-staging", action="store_true", help="Remove staging directory after successful load")
    p.add_argument(
        "--rm-source-xml",
        action="store_true",
        help="Delete source XML after successful load. note: this breaks --force-shard/shard-count "
        "changes unless the files are re-extracted or re-downloaded first",
    )
    p.set_defaults(func=cmd_pipeline)


def _add_shard_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "shard",
        help="Shard an XML file into CSV parts",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--xml", required=True, type=Path, help="Path to <table>.xml")
    p.add_argument("--site", help="Defaults --out-dir to data/staging/<site>/<table> if unset")
    p.add_argument("--schema-dir", type=Path, default=None, help="Defaults to db/schema/<table>")
    p.add_argument("--out-dir", type=Path, default=None, help="Defaults to data/staging/<site>/<table>; needs --site")
    p.add_argument("--shards", type=positive_int, default=8, help="Number of output shards")
    p.add_argument("--shard-workers", type=positive_int, default=1, help="Parallel XML shard workers")
    p.add_argument("--max-rows-per-part", type=int, default=5_000_000, help="Rows per CSV part file")
    p.set_defaults(func=cmd_shard)


def _add_load_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "load",
        help="Load CSV parts listed in a manifest into Postgres",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    _add_pg_args(p)
    p.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help="Path to manifest.json (data/staging/<site>/<table>/manifest.json)",
    )
    p.add_argument("--ddl", type=Path, help="Path to DDL SQL file (db/ddl/postgres/create_<table>.sql)")
    p.add_argument("--truncate-first", action="store_true", help="Truncate table before loading")
    p.add_argument("--load-workers", type=positive_int, default=1, help="Parallel COPY workers")
    p.add_argument("--delimiter", default=",", help="CSV delimiter")
    p.add_argument("--rm-staging", action="store_true", help="Delete staging directory after successful load")
    p.set_defaults(func=cmd_load)


def _add_ddl_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "ddl",
        help="Generate a CREATE TABLE SQL file from a schema.yml",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--table", help="Table name. If set, defaults to paths under db/")
    p.add_argument("--schema-dir", type=Path, default=None, help="Defaults to db/schema/<table>")
    p.add_argument("--out-sql", type=Path, default=None, help="Defaults to db/ddl/postgres/create_<table>.sql")
    p.set_defaults(func=cmd_ddl)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="sepg", description="StackExchange data importer for PostgreSQL")
    sub = ap.add_subparsers(dest="command", required=True)

    _add_download_parser(sub)
    _add_pipeline_parser(sub)
    _add_shard_parser(sub)
    _add_load_parser(sub)
    _add_ddl_parser(sub)

    return ap


def main(argv: list[str] | None = None) -> None:
    ap = build_parser()
    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
