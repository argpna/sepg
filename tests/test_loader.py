from pathlib import Path

import psycopg2
import pytest
from psycopg2 import sql

import sepg.loader as loader
from sepg.loader import (
    LoadConfig,
    PgConn,
    _retry_on_operational_error,
    apply_ddl,
    build_dsn,
    copy_part,
    ensure_database,
    ensure_schema,
    load_manifest,
    truncate_table,
)
from sepg.manifest import Manifest, ManifestPart


def test_retry_succeeds_after_transient_operational_errors(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    calls = []

    @_retry_on_operational_error(attempts=3)
    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise psycopg2.OperationalError("connection refused")
        return "ok"

    assert flaky() == "ok"
    assert len(calls) == 3


def test_retry_gives_up_after_max_attempts(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    calls = []

    @_retry_on_operational_error(attempts=3)
    def always_fails():
        calls.append(1)
        raise psycopg2.OperationalError("connection refused")

    with pytest.raises(psycopg2.OperationalError):
        always_fails()
    assert len(calls) == 3


def test_retry_does_not_catch_non_operational_errors(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    calls = []

    @_retry_on_operational_error(attempts=3)
    def bad_query():
        calls.append(1)
        raise psycopg2.ProgrammingError("syntax error")

    with pytest.raises(psycopg2.ProgrammingError):
        bad_query()
    assert len(calls) == 1


def _render(query) -> str:
    """Render a plain string or a psycopg2.sql.Composable back to text, without going through
    psycopg2's C-level quote_ident (which requires a real server connection) - good enough to
    assert identifiers/literals ended up in the right place."""
    if isinstance(query, str):
        return query
    if isinstance(query, sql.Composed):
        return "".join(_render(part) for part in query.seq)
    if isinstance(query, sql.SQL):
        return query.string
    if isinstance(query, sql.Identifier):
        return ".".join(f'"{s}"' for s in query.strings)
    if isinstance(query, sql.Literal):
        return repr(query.wrapped)
    return str(query)


class FakeCursor:
    def __init__(self, conn: "FakeConnection"):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        rendered = _render(query)
        if self.conn.raise_on and self.conn.raise_on(rendered):
            raise self.conn.raise_on_exc
        self.conn.executed.append((rendered, params))

    def fetchone(self):
        if self.conn.fetchone_queue:
            return self.conn.fetchone_queue.pop(0)
        return None

    def copy_expert(self, copy_sql, file):
        self.conn.copy_calls.append((_render(copy_sql), file.read()))


class FakeConnection:
    def __init__(self, dsn, fetchone_results=None):
        self.dsn = dsn
        self.autocommit = False
        self.executed: list[tuple[str, object]] = []
        self.copy_calls: list[tuple[str, bytes]] = []
        self.committed = False
        self.closed = False
        self.fetchone_queue = list(fetchone_results or [])
        self.raise_on = None
        self.raise_on_exc = None

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


@pytest.fixture
def fake_connect(monkeypatch):
    def factory(fetchone_results=None, raise_on=None, raise_on_exc=None):
        created: list[FakeConnection] = []

        def _connect(dsn):
            conn = FakeConnection(dsn, fetchone_results=fetchone_results)
            conn.raise_on = raise_on
            conn.raise_on_exc = raise_on_exc
            created.append(conn)
            return conn

        monkeypatch.setattr(loader.psycopg2, "connect", _connect)
        return created

    return factory


def _pgconn(**overrides) -> PgConn:
    defaults = dict(host="localhost", port=5432, user="se", password="sepass", database="vi", schema="public")
    defaults.update(overrides)
    return PgConn(**defaults)


def test_build_dsn_includes_core_fields_and_application_name():
    conn = _pgconn()
    dsn = build_dsn(conn)
    assert "dbname=vi" in dsn
    assert "user=se" in dsn
    assert "password=sepass" in dsn
    assert "host=localhost" in dsn
    assert "port=5432" in dsn
    assert "application_name=sepg" in dsn


def test_build_dsn_target_db_overrides_conn_database():
    conn = _pgconn(database="vi")
    dsn = build_dsn(conn, target_db="postgres")
    assert "dbname=postgres" in dsn
    assert "dbname=vi" not in dsn


def test_build_dsn_omits_application_name_when_none():
    conn = _pgconn(application_name=None)
    dsn = build_dsn(conn)
    assert "application_name" not in dsn


def test_ensure_database_creates_from_template_when_missing(fake_connect):
    connections = fake_connect(fetchone_results=[None, (1,)])
    conn = _pgconn(database="vi")

    ensure_database(conn)

    fc = connections[0]
    assert fc.autocommit is True
    assert fc.closed is True
    rendered = [text for text, _params in fc.executed]
    assert len(rendered) == 3
    assert "CREATE DATABASE" in rendered[-1]
    assert '"vi"' in rendered[-1]
    assert '"se_template"' in rendered[-1]


def test_ensure_database_skips_when_already_exists(fake_connect):
    connections = fake_connect(fetchone_results=[(1,)])
    conn = _pgconn(database="vi")

    ensure_database(conn)

    fc = connections[0]
    assert len(fc.executed) == 1  # only the existence check, no CREATE DATABASE


def test_ensure_database_raises_when_template_equals_target(fake_connect):
    fake_connect(fetchone_results=[None])
    conn = _pgconn(database="se_template", template_database="se_template")

    with pytest.raises(SystemExit, match="cannot be created from itself"):
        ensure_database(conn)


def test_ensure_database_raises_when_template_missing(fake_connect):
    fake_connect(fetchone_results=[None, None])
    conn = _pgconn(database="vi", template_database="ghost_template")

    with pytest.raises(SystemExit, match="does not exist"):
        ensure_database(conn)


def test_ensure_database_creates_without_template_when_none_configured(fake_connect):
    connections = fake_connect(fetchone_results=[None])
    conn = _pgconn(database="vi", template_database=None)

    ensure_database(conn)

    fc = connections[0]
    rendered = [text for text, _params in fc.executed]
    assert len(rendered) == 2
    assert "CREATE DATABASE" in rendered[-1]
    assert "TEMPLATE" not in rendered[-1]


def test_ensure_schema_creates_schema_and_sets_owner(fake_connect):
    connections = fake_connect()
    conn = _pgconn(schema="public", user="se")

    ensure_schema(conn)

    fc = connections[0]
    assert fc.autocommit is True
    assert fc.closed is True
    rendered = [text for text, _params in fc.executed]
    assert any("CREATE SCHEMA IF NOT EXISTS" in r and '"public"' in r for r in rendered)
    assert any("ALTER SCHEMA" in r and '"public"' in r and '"se"' in r for r in rendered)


def test_ensure_schema_warns_but_does_not_raise_when_alter_owner_fails(fake_connect, monkeypatch):
    fake_connect(raise_on=lambda rendered: "ALTER SCHEMA" in rendered, raise_on_exc=RuntimeError("no perms"))
    conn = _pgconn(schema="public", user="se")
    warnings = []
    monkeypatch.setattr(loader, "warn", warnings.append)

    ensure_schema(conn)  # must not raise

    assert len(warnings) == 1
    assert "ALTER SCHEMA owner" in warnings[0]


def test_apply_ddl_is_noop_when_ddl_path_is_none(monkeypatch):
    def fail_if_called(dsn):
        raise AssertionError("psycopg2.connect should not be called when ddl_path is None")

    monkeypatch.setattr(loader.psycopg2, "connect", fail_if_called)
    conn = _pgconn()

    apply_ddl(conn, None)  # must not raise / must not connect


def test_apply_ddl_executes_ddl_text_with_search_path(fake_connect, tmp_path):
    connections = fake_connect()
    conn = _pgconn(schema="public")
    ddl_path = tmp_path / "create_posts.sql"
    ddl_path.write_text("CREATE TABLE posts (id integer);\n", encoding="utf-8")

    apply_ddl(conn, ddl_path)

    fc = connections[0]
    assert fc.committed is True
    assert fc.closed is True
    rendered = [text for text, _params in fc.executed]
    assert any("SET LOCAL search_path" in r and '"public"' in r for r in rendered)
    assert ddl_path.read_text(encoding="utf-8") in rendered


def test_truncate_table_executes_qualified_truncate(fake_connect):
    connections = fake_connect()
    conn = _pgconn(schema="public")

    truncate_table(conn, table="posts")

    fc = connections[0]
    assert fc.committed is True
    rendered = fc.executed[0][0]
    assert "TRUNCATE" in rendered
    assert '"public"."posts"' in rendered
    assert "RESTART IDENTITY" in rendered


@pytest.fixture
def patch_quote_ident(monkeypatch):
    """copy_part renders its COPY statement via Composed.as_string(conn) before handing it to
    cur.copy_expert, and psycopg2's real quote_ident()/Literal.as_string() reject anything that
    isn't an actual connection/cursor. Swap in pure-Python equivalents so a FakeConnection
    can stand in for real quoting/escaping."""

    def fake_quote_ident(value, _scope):
        return '"' + value.replace('"', '""') + '"'

    def fake_literal_as_string(self, _context):
        return "'" + str(self.wrapped).replace("'", "''") + "'"

    monkeypatch.setattr(psycopg2.extensions, "quote_ident", fake_quote_ident)
    monkeypatch.setattr(sql.Literal, "as_string", fake_literal_as_string)


def test_copy_part_executes_copy_and_returns_path_and_size(fake_connect, patch_quote_ident, tmp_path):
    connections = fake_connect()
    conn = _pgconn(schema="public")
    part_path = tmp_path / "shard-00-000001.csv"
    part_path.write_text("id,title\n1,a\n2,b\n", encoding="utf-8")

    path, size = copy_part(conn, table="posts", columns=["id", "title"], part_path=part_path, delimiter=",")

    assert path == str(part_path)
    assert size == part_path.stat().st_size
    fc = connections[0]
    assert fc.committed is True
    assert fc.closed is True
    assert any("SET application_name" in text for text, _params in fc.executed)
    assert len(fc.copy_calls) == 1
    copy_sql, file_bytes = fc.copy_calls[0]
    assert "COPY" in copy_sql
    assert '"public"."posts"' in copy_sql
    assert '"id", "title"' in copy_sql
    assert file_bytes == part_path.read_bytes()


def test_copy_part_returns_zero_size_when_stat_fails(fake_connect, patch_quote_ident, tmp_path, monkeypatch):
    fake_connect()
    conn = _pgconn()
    part_path = tmp_path / "shard-00-000001.csv"
    part_path.write_text("id\n1\n", encoding="utf-8")

    def broken_stat(path):
        raise OSError("gone")

    monkeypatch.setattr(loader.os, "stat", broken_stat)

    _path, size = copy_part(conn, table="posts", columns=["id"], part_path=part_path)

    assert size == 0


def _write_manifest_with_parts(tmp_path, *, rows=(3, 2)) -> Path:
    manifest_path = tmp_path / "manifest.json"
    parts = []
    row_start = 1
    for i, n in enumerate(rows):
        rel = f"shard-0{i}-000001.csv"
        lines = ["id,title"] + [f"{row_start + j},v{row_start + j}" for j in range(n)]
        (tmp_path / rel).write_text("\n".join(lines) + "\n", encoding="utf-8")
        parts.append(ManifestPart(path=rel, rows=n, bytes=len(lines), status="created"))
        row_start += n

    manifest = Manifest(
        table="posts",
        primary_key="id",
        columns=["id", "title"],
        source_xml="/data/xml/vi/Posts.xml",
        shards=len(rows),
        parts=parts,
        total_rows=sum(rows),
    )
    manifest.write(manifest_path)
    return manifest_path


def test_load_manifest_sequential_applies_ddl_truncates_and_copies_every_part(monkeypatch, tmp_path):
    manifest_path = _write_manifest_with_parts(tmp_path, rows=(3, 2))
    ddl_calls = []
    truncate_calls = []
    copy_calls = []

    monkeypatch.setattr(loader, "apply_ddl", lambda conn, ddl_path: ddl_calls.append(ddl_path))
    monkeypatch.setattr(loader, "truncate_table", lambda conn, *, table: truncate_calls.append(table))
    monkeypatch.setattr(
        loader,
        "copy_part",
        lambda conn, *, table, columns, part_path, delimiter=",": (
            copy_calls.append((table, tuple(columns), part_path.name, delimiter))
            or (str(part_path), part_path.stat().st_size)
        ),
    )

    conn = _pgconn()
    ddl_path = tmp_path / "create_posts.sql"
    cfg = LoadConfig(load_workers=1, delimiter=",", truncate_first=True)

    load_manifest(manifest_path=manifest_path, ddl_path=ddl_path, conn=conn, cfg=cfg)

    assert ddl_calls == [ddl_path]
    assert truncate_calls == ["posts"]
    assert len(copy_calls) == 2
    assert {c[2] for c in copy_calls} == {"shard-00-000001.csv", "shard-01-000001.csv"}
    assert all(c[0] == "posts" and c[1] == ("id", "title") for c in copy_calls)


class FakePool:
    def __init__(self, _processes):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def imap_unordered(self, fn, jobs, chunksize=1):
        return [fn(j) for j in jobs]


def test_load_manifest_parallel_path_copies_every_part(monkeypatch, tmp_path):
    manifest_path = _write_manifest_with_parts(tmp_path, rows=(3, 2))
    copy_calls = []

    monkeypatch.setattr(loader, "apply_ddl", lambda conn, ddl_path: None)
    monkeypatch.setattr(loader.mp, "Pool", FakePool)
    monkeypatch.setattr(
        loader,
        "copy_part",
        lambda conn, *, table, columns, part_path, delimiter=",": (
            copy_calls.append(part_path.name) or (str(part_path), part_path.stat().st_size)
        ),
    )

    conn = _pgconn()
    cfg = LoadConfig(load_workers=2, delimiter=",", truncate_first=False)

    load_manifest(manifest_path=manifest_path, ddl_path=None, conn=conn, cfg=cfg)

    assert set(copy_calls) == {"shard-00-000001.csv", "shard-01-000001.csv"}


def test_load_manifest_raises_when_a_part_file_is_missing(monkeypatch, tmp_path):
    manifest_path = _write_manifest_with_parts(tmp_path, rows=(3, 2))
    (tmp_path / "shard-01-000001.csv").unlink()
    monkeypatch.setattr(loader, "apply_ddl", lambda conn, ddl_path: None)

    conn = _pgconn()
    cfg = LoadConfig(load_workers=1)

    with pytest.raises(FileNotFoundError, match="CSV part missing"):
        load_manifest(manifest_path=manifest_path, ddl_path=None, conn=conn, cfg=cfg)


def test_load_manifest_logs_bytes_only_when_no_rows_hint(monkeypatch, tmp_path):
    manifest_path = tmp_path / "manifest.json"
    (tmp_path / "shard-00-000001.csv").write_text("id\n1\n", encoding="utf-8")
    manifest = Manifest(
        table="posts",
        primary_key="id",
        columns=["id"],
        source_xml="/data/xml/vi/Posts.xml",
        shards=1,
        parts=[ManifestPart(path="shard-00-000001.csv", rows=None, bytes=None, status="created")],
        total_rows=0,
    )
    manifest.write(manifest_path)

    monkeypatch.setattr(loader, "apply_ddl", lambda conn, ddl_path: None)
    monkeypatch.setattr(
        loader,
        "copy_part",
        lambda conn, *, table, columns, part_path, delimiter=",": (str(part_path), part_path.stat().st_size),
    )
    messages = []
    monkeypatch.setattr(loader, "step", lambda prefix, msg: messages.append(msg))

    conn = _pgconn()
    load_manifest(manifest_path=manifest_path, ddl_path=None, conn=conn, cfg=LoadConfig(load_workers=1))

    done_messages = [m for m in messages if m.startswith("Loaded")]
    assert len(done_messages) == 1
    assert "(bytes " in done_messages[0]
    assert "rows" not in done_messages[0]
