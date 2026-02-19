from pathlib import Path

import pytest

import sepg.pipeline as pipeline
from sepg.manifest import Manifest
from sepg.pipeline import PipelineArgs, _need_atomic_reshard, process_table, resolve_tables, run_pipeline


def _write_manifest(path: Path, *, shards: int, source_xml: str) -> None:
    manifest = Manifest(
        table="posts",
        primary_key="id",
        columns=["id"],
        source_xml=source_xml,
        shards=shards,
        parts=[],
        total_rows=0,
    )
    manifest.write(path)


def test_forced_reshard_always_wins(tmp_path):
    xml_path = tmp_path / "Posts.xml"
    xml_path.write_text("<posts/>")
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, shards=4, source_xml=str(xml_path))

    need, reason = _need_atomic_reshard(manifest_path=manifest_path, xml_path=xml_path, requested_shards=4, force=True)

    assert need is True
    assert reason == "--force-shard"


def test_no_manifest_requires_reshard(tmp_path):
    xml_path = tmp_path / "Posts.xml"
    xml_path.write_text("<posts/>")
    manifest_path = tmp_path / "does-not-exist" / "manifest.json"

    need, reason = _need_atomic_reshard(manifest_path=manifest_path, xml_path=xml_path, requested_shards=4, force=False)

    assert need is True
    assert reason == "no manifest"


def test_unreadable_manifest_requires_reshard(tmp_path):
    xml_path = tmp_path / "Posts.xml"
    xml_path.write_text("<posts/>")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("not valid json{{{")

    need, reason = _need_atomic_reshard(manifest_path=manifest_path, xml_path=xml_path, requested_shards=4, force=False)

    assert need is True
    assert reason == "manifest unreadable"


def test_manifest_missing_required_key_requires_reshard(tmp_path):
    xml_path = tmp_path / "Posts.xml"
    xml_path.write_text("<posts/>")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text('{"columns": ["id"]}')  # valid JSON, missing required "table" key

    need, reason = _need_atomic_reshard(manifest_path=manifest_path, xml_path=xml_path, requested_shards=4, force=False)

    assert need is True
    assert reason == "manifest unreadable"


def test_shard_count_mismatch_requires_reshard(tmp_path):
    xml_path = tmp_path / "Posts.xml"
    xml_path.write_text("<posts/>")
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, shards=4, source_xml=str(xml_path))

    need, reason = _need_atomic_reshard(manifest_path=manifest_path, xml_path=xml_path, requested_shards=8, force=False)

    assert need is True
    assert "shards mismatch" in reason


def test_source_xml_mismatch_requires_reshard(tmp_path):
    old_xml = tmp_path / "OldPosts.xml"
    old_xml.write_text("<posts/>")
    new_xml = tmp_path / "Posts.xml"
    new_xml.write_text("<posts/>")
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, shards=4, source_xml=str(old_xml))

    need, reason = _need_atomic_reshard(manifest_path=manifest_path, xml_path=new_xml, requested_shards=4, force=False)

    assert need is True
    assert "source_xml mismatch" in reason


def test_matching_manifest_skips_reshard(tmp_path):
    xml_path = tmp_path / "Posts.xml"
    xml_path.write_text("<posts/>")
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, shards=4, source_xml=str(xml_path))

    need, reason = _need_atomic_reshard(manifest_path=manifest_path, xml_path=xml_path, requested_shards=4, force=False)

    assert need is False
    assert reason == ""


def test_resolve_tables_rejects_both_all_and_tables():
    with pytest.raises(SystemExit, match="either --all or --tables"):
        resolve_tables(all_tables=True, tables_csv="posts")


def test_resolve_tables_requires_one_of_all_or_tables():
    with pytest.raises(SystemExit, match="Provide --all or --tables"):
        resolve_tables(all_tables=False, tables_csv=None)


def test_resolve_tables_all_delegates_to_list_schema_tables(monkeypatch):
    monkeypatch.setattr(pipeline, "list_schema_tables", lambda: ["badges", "posts"])
    assert resolve_tables(all_tables=True, tables_csv=None) == ["badges", "posts"]


def test_resolve_tables_splits_strips_lowercases_and_drops_empties():
    result = resolve_tables(all_tables=False, tables_csv="Badges, posts ,,Votes")
    assert result == ["badges", "posts", "votes"]


def _pargs(**overrides) -> PipelineArgs:
    defaults = dict(site="vi", tables=["posts"], shards=2, force_shard=False, rm_staging=False)
    defaults.update(overrides)
    return PipelineArgs(**defaults)


def test_process_table_skips_when_schema_dir_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "schema_dir", lambda: tmp_path / "no-such-schema-root")
    monkeypatch.setattr(pipeline, "emit_ddl", lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not run")))
    warnings = []
    monkeypatch.setattr(pipeline, "warn", warnings.append)

    process_table(table="posts", pargs=_pargs(), pconn=object())

    assert any("schema dir missing" in w for w in warnings)


def test_process_table_reuses_existing_manifest_without_resharding(tmp_path, monkeypatch):
    schema_root = tmp_path / "schema"
    (schema_root / "posts").mkdir(parents=True)
    xml_path = tmp_path / "Posts.xml"
    xml_path.write_text("<posts/>", encoding="utf-8")
    staging_root = tmp_path / "staging"
    final_dir = staging_root / "vi" / "posts"
    final_dir.mkdir(parents=True)
    manifest_path = final_dir / "manifest.json"
    Manifest(
        table="posts",
        primary_key="id",
        columns=["id"],
        source_xml=str(xml_path),
        shards=2,
        parts=[],
        total_rows=0,
    ).write(manifest_path)

    monkeypatch.setattr(pipeline, "schema_dir", lambda: schema_root)
    monkeypatch.setattr(pipeline, "ddl_dir", lambda: tmp_path / "ddl")
    monkeypatch.setattr(pipeline, "staging_dir", lambda: staging_root)
    monkeypatch.setattr(pipeline, "pick_xml_path", lambda site, table: xml_path)
    ddl_calls = []
    monkeypatch.setattr(pipeline, "emit_ddl", lambda schema_dir, out_sql: ddl_calls.append(out_sql) or out_sql)
    monkeypatch.setattr(pipeline, "shard_xml", lambda **k: (_ for _ in ()).throw(AssertionError("should not reshard")))
    load_calls = []
    monkeypatch.setattr(
        pipeline,
        "load_manifest",
        lambda *, manifest_path, ddl_path, conn, cfg: load_calls.append((manifest_path, ddl_path, conn, cfg)),
    )

    conn = object()
    process_table(table="posts", pargs=_pargs(shards=2, rm_staging=False), pconn=conn)

    assert len(load_calls) == 1
    called_manifest_path, called_ddl_path, called_conn, _cfg = load_calls[0]
    assert called_manifest_path == manifest_path
    assert called_conn is conn
    assert called_ddl_path == ddl_calls[0]


def test_process_table_reshards_and_atomically_swaps_staging_dir(tmp_path, monkeypatch):
    schema_root = tmp_path / "schema"
    (schema_root / "posts").mkdir(parents=True)
    xml_path = tmp_path / "Posts.xml"
    xml_path.write_text("<posts/>", encoding="utf-8")
    staging_root = tmp_path / "staging"
    final_dir = staging_root / "vi" / "posts"

    monkeypatch.setattr(pipeline, "schema_dir", lambda: schema_root)
    monkeypatch.setattr(pipeline, "ddl_dir", lambda: tmp_path / "ddl")
    monkeypatch.setattr(pipeline, "staging_dir", lambda: staging_root)
    monkeypatch.setattr(pipeline, "pick_xml_path", lambda site, table: xml_path)
    monkeypatch.setattr(pipeline, "emit_ddl", lambda schema_dir, out_sql: out_sql)

    def fake_shard_xml(*, xml_path, schema_dir, out_dir, cfg):
        assert out_dir.name.startswith("posts.tmp-")
        Manifest(
            table="posts",
            primary_key="id",
            columns=["id"],
            source_xml=str(xml_path),
            shards=cfg.shards,
            parts=[],
            total_rows=0,
        ).write(out_dir / "manifest.json")

    monkeypatch.setattr(pipeline, "shard_xml", fake_shard_xml)
    load_calls = []
    monkeypatch.setattr(
        pipeline,
        "load_manifest",
        lambda *, manifest_path, ddl_path, conn, cfg: load_calls.append(manifest_path),
    )

    process_table(table="posts", pargs=_pargs(shards=2), pconn=object())

    assert final_dir.exists()
    assert (final_dir / "manifest.json").exists()
    assert not list(staging_root.glob("vi/posts.tmp-*"))
    assert load_calls == [final_dir / "manifest.json"]


def test_process_table_cleans_up_tmp_dir_when_shard_fails(tmp_path, monkeypatch):
    schema_root = tmp_path / "schema"
    (schema_root / "posts").mkdir(parents=True)
    xml_path = tmp_path / "Posts.xml"
    xml_path.write_text("<posts/>", encoding="utf-8")
    staging_root = tmp_path / "staging"

    monkeypatch.setattr(pipeline, "schema_dir", lambda: schema_root)
    monkeypatch.setattr(pipeline, "ddl_dir", lambda: tmp_path / "ddl")
    monkeypatch.setattr(pipeline, "staging_dir", lambda: staging_root)
    monkeypatch.setattr(pipeline, "pick_xml_path", lambda site, table: xml_path)
    monkeypatch.setattr(pipeline, "emit_ddl", lambda schema_dir, out_sql: out_sql)

    def failing_shard_xml(*, xml_path, schema_dir, out_dir, cfg):
        raise RuntimeError("boom")

    monkeypatch.setattr(pipeline, "shard_xml", failing_shard_xml)

    with pytest.raises(RuntimeError, match="boom"):
        process_table(table="posts", pargs=_pargs(shards=2), pconn=object())

    assert not list((staging_root / "vi").glob("posts.tmp-*"))


def test_process_table_removes_staging_dir_when_requested(tmp_path, monkeypatch):
    schema_root = tmp_path / "schema"
    (schema_root / "posts").mkdir(parents=True)
    xml_path = tmp_path / "Posts.xml"
    xml_path.write_text("<posts/>", encoding="utf-8")
    staging_root = tmp_path / "staging"
    final_dir = staging_root / "vi" / "posts"
    final_dir.mkdir(parents=True)
    manifest_path = final_dir / "manifest.json"
    Manifest(
        table="posts", primary_key="id", columns=["id"], source_xml=str(xml_path), shards=2, parts=[], total_rows=0
    ).write(manifest_path)

    monkeypatch.setattr(pipeline, "schema_dir", lambda: schema_root)
    monkeypatch.setattr(pipeline, "ddl_dir", lambda: tmp_path / "ddl")
    monkeypatch.setattr(pipeline, "staging_dir", lambda: staging_root)
    monkeypatch.setattr(pipeline, "pick_xml_path", lambda site, table: xml_path)
    monkeypatch.setattr(pipeline, "emit_ddl", lambda schema_dir, out_sql: out_sql)
    monkeypatch.setattr(pipeline, "load_manifest", lambda **k: None)
    rm_calls = []
    monkeypatch.setattr(pipeline, "remove_staging_dir", lambda path: rm_calls.append(path))

    process_table(table="posts", pargs=_pargs(shards=2, rm_staging=True), pconn=object())

    assert rm_calls == [manifest_path]


def test_run_pipeline_ensures_db_and_processes_every_table(monkeypatch):
    calls = []
    monkeypatch.setattr(pipeline, "ensure_database", lambda conn: calls.append(("ensure_database", conn)))
    monkeypatch.setattr(pipeline, "ensure_schema", lambda conn: calls.append(("ensure_schema", conn)))
    monkeypatch.setattr(
        pipeline,
        "process_table",
        lambda *, table, pargs, pconn: calls.append(("process_table", table)),
    )

    conn = object()
    pargs = _pargs(tables=["badges", "posts"])
    run_pipeline(pargs=pargs, pconn=conn)

    assert calls == [
        ("ensure_database", conn),
        ("ensure_schema", conn),
        ("process_table", "badges"),
        ("process_table", "posts"),
    ]
