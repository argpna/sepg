import functools
import multiprocessing as mp
import os
import time
from dataclasses import dataclass
from pathlib import Path

import psycopg2
from psycopg2 import sql

from .log import step, warn
from .manifest import Manifest, ManifestPart


def _retry_on_operational_error(attempts: int = 3):
    """Retry a DB call on psycopg2.OperationalError (dropped/refused connections).
    Only covers connect-time and mid-session connection loss, not query errors,
    so a bad DDL/COPY statement still fails fast instead of retrying 3x.
    """

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc: BaseException = RuntimeError("unreachable")
            for attempt in range(attempts):
                if attempt > 0:
                    time.sleep(2 ** (attempt - 1))
                try:
                    return fn(*args, **kwargs)
                except psycopg2.OperationalError as e:
                    last_exc = e
            raise last_exc

        return wrapper

    return decorator


@dataclass(frozen=True)
class PgConn:
    host: str
    port: int
    user: str
    password: str
    database: str
    schema: str

    template_database: str | None = "se_template"
    maintenance_db: str = "postgres"
    application_name: str | None = "sepg"


def build_dsn(conn: PgConn, *, target_db: str | None = None) -> str:
    dbname = target_db or conn.database
    base = f"dbname={dbname} user={conn.user} password={conn.password} host={conn.host} port={conn.port}"
    if conn.application_name:
        base += f" application_name={conn.application_name}"
    return base


@_retry_on_operational_error()
def ensure_database(conn: PgConn) -> None:
    maint_dsn = build_dsn(conn, target_db=conn.maintenance_db)

    c = psycopg2.connect(maint_dsn)
    try:
        c.autocommit = True
        with c.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname=%s", (conn.database,))
            if cur.fetchone():
                return

            tmpl = conn.template_database
            if tmpl and tmpl == conn.database:
                raise SystemExit(f"[err] database '{conn.database}' cannot be created from itself as a template")

            if tmpl:
                cur.execute("SELECT 1 FROM pg_database WHERE datname=%s", (tmpl,))
                if not cur.fetchone():
                    raise SystemExit(f"[err] template database '{tmpl}' does not exist")

                step("ensure", f"creating database {conn.database} from template {tmpl}")
                cur.execute(
                    sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                        sql.Identifier(conn.database),
                        sql.Identifier(tmpl),
                    )
                )
            else:
                step("ensure", f"creating database {conn.database}")
                cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(conn.database)))
    finally:
        c.close()


@_retry_on_operational_error()
def ensure_schema(conn: PgConn) -> None:
    c = psycopg2.connect(build_dsn(conn))
    try:
        c.autocommit = True
        with c.cursor() as cur:
            cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(conn.schema)))
            try:
                cur.execute(
                    sql.SQL("ALTER SCHEMA {} OWNER TO {}").format(
                        sql.Identifier(conn.schema),
                        sql.Identifier(conn.user),
                    )
                )
            except Exception as e:
                warn(f"ALTER SCHEMA owner to {conn.user} failed: {e}")
    finally:
        c.close()


@_retry_on_operational_error()
def apply_ddl(conn: PgConn, ddl_path: Path | None) -> None:
    if not ddl_path:
        return

    ddl_text = Path(ddl_path).read_text(encoding="utf-8")

    c = psycopg2.connect(build_dsn(conn))
    try:
        with c.cursor() as cur:
            cur.execute(sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(conn.schema)))
            cur.execute(ddl_text)
        c.commit()
    finally:
        c.close()

    step("ddl", f"applied {ddl_path} with search_path={conn.schema}")


@_retry_on_operational_error()
def truncate_table(conn: PgConn, *, table: str) -> None:
    c = psycopg2.connect(build_dsn(conn))
    try:
        with c.cursor() as cur:
            cur.execute(
                sql.SQL("TRUNCATE {}.{} RESTART IDENTITY").format(
                    sql.Identifier(conn.schema),
                    sql.Identifier(table),
                )
            )
        c.commit()
    finally:
        c.close()

    step("truncate", f"{conn.schema}.{table}")


@_retry_on_operational_error()
def copy_part(
    conn: PgConn,
    *,
    table: str,
    columns: list[str],
    part_path: Path,
    delimiter: str = ",",
) -> tuple[str, int]:
    c = psycopg2.connect(build_dsn(conn))
    try:
        with c.cursor() as cur:
            cur.execute(
                "SET application_name = %s",
                (f"sepg:{table}:pid:{os.getpid()}",),
            )

            qualified_table = sql.SQL("{}.{}").format(
                sql.Identifier(conn.schema),
                sql.Identifier(table),
            )
            collist = sql.SQL(", ").join(sql.Identifier(cn) for cn in columns)

            copy_stmt = sql.SQL(
                "COPY {tbl} ({cols}) FROM STDIN WITH (FORMAT csv, HEADER true, DELIMITER {delim})"
            ).format(
                tbl=qualified_table,
                cols=collist,
                delim=sql.Literal(delimiter),
            )

            with open(part_path, "rb") as f:
                cur.copy_expert(copy_stmt.as_string(c), f)

        c.commit()
    finally:
        c.close()

    try:
        size = os.stat(part_path).st_size
    except OSError:
        size = 0

    return (str(part_path), size)


def _worker(job):
    conn, table, columns, abs_part_path, delimiter, rows_hint = job
    path, size = copy_part(
        conn,
        table=table,
        columns=columns,
        part_path=Path(abs_part_path),
        delimiter=delimiter,
    )
    return (path, rows_hint, size)


@dataclass(frozen=True)
class LoadConfig:
    load_workers: int = 1
    delimiter: str = ","
    truncate_first: bool = False


def _resolve_part(manifest_path: Path, manifest: Manifest, part: ManifestPart) -> Path:
    abs_path = manifest.resolve_part_path(manifest_path, part)
    if not abs_path.exists():
        raise FileNotFoundError(f"CSV part missing: {abs_path}")
    return abs_path


def load_manifest(
    *,
    manifest_path: Path,
    ddl_path: Path | None,
    conn: PgConn,
    cfg: LoadConfig,
) -> None:
    manifest = Manifest.read(manifest_path)

    table = str(manifest.table).lower()
    columns = [str(c).lower() for c in manifest.columns]
    if not columns:
        raise SystemExit("[err] manifest missing 'columns' list")

    apply_ddl(conn, ddl_path)

    if cfg.truncate_first:
        truncate_table(conn, table=table)

    rows_map: dict[str, int | None] = {p.path: p.rows for p in manifest.parts}

    parts_rel = [p.path for p in manifest.parts]
    parts_abs = {p.path: _resolve_part(manifest_path, manifest, p) for p in manifest.parts}

    jobs = [(conn, table, columns, str(parts_abs[rel]), cfg.delimiter, rows_map.get(rel)) for rel in parts_rel]

    total_rows = 0
    total_bytes = 0
    any_rows_hint = any(v is not None for v in rows_map.values())

    if cfg.load_workers > 1:
        with mp.Pool(cfg.load_workers) as pool:
            for abs_path, rows_hint, size in pool.imap_unordered(_worker, jobs, chunksize=1):
                total_bytes += size or 0
                rel_path = Path(abs_path).name
                if rows_hint is not None:
                    total_rows += rows_hint
                    step("copy", f"{rel_path} -> {conn.schema}.{table}  rows={rows_hint:,}")
                else:
                    step("copy", f"{rel_path} -> {conn.schema}.{table}")
    else:
        for j in jobs:
            abs_path, rows_hint, size = _worker(j)
            total_bytes += size or 0
            rel_path = Path(abs_path).name
            if rows_hint is not None:
                total_rows += rows_hint
                step("copy", f"{rel_path} -> {conn.schema}.{table}  rows={rows_hint:,}")
            else:
                step("copy", f"{rel_path} -> {conn.schema}.{table}")

    if any_rows_hint:
        step(
            "done",
            f"Loaded {len(parts_rel)} part(s) into {conn.schema}.{table} "
            f"(manifest rows {total_rows:,}, bytes {total_bytes:,})",
        )
    else:
        step("done", f"Loaded {len(parts_rel)} part(s) into {conn.schema}.{table} (bytes {total_bytes:,})")
