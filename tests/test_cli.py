import argparse

import pytest

import sepg.cli as cli
from sepg.cli import build_parser, positive_int


def test_positive_int_accepts_positive_values():
    assert positive_int("1") == 1
    assert positive_int("42") == 42


def test_positive_int_rejects_zero():
    with pytest.raises(argparse.ArgumentTypeError):
        positive_int("0")


def test_positive_int_rejects_negative():
    with pytest.raises(argparse.ArgumentTypeError):
        positive_int("-3")


def test_positive_int_rejects_non_numeric():
    with pytest.raises(argparse.ArgumentTypeError):
        positive_int("abc")


def test_build_parser_exposes_all_five_subcommands():
    parser = build_parser()
    subparsers_action = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    assert set(subparsers_action.choices.keys()) == {"download", "pipeline", "shard", "load", "ddl"}


def test_build_parser_pipeline_defaults():
    args = build_parser().parse_args(["pipeline", "--site", "vi", "--all"])
    assert args.shards == 8
    assert args.shard_workers == 1
    assert args.load_workers >= 1
    assert args.truncate_first is False
    assert args.force_shard is False
    assert args.rm_staging is False
    assert args.host == "localhost"
    assert args.port == 5432


def test_build_parser_pipeline_requires_site():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["pipeline", "--all"])


def test_build_parser_download_defaults():
    args = build_parser().parse_args(["download", "--torrent", "https://example.com/x.torrent"])
    assert args.rpc_url == "http://transmission:9091/transmission/rpc"
    assert args.wait_seconds == 604800
    assert args.poll == 1.0
    assert args.out_dir is None
    assert args.list_files is False


def test_build_parser_shard_workers_rejects_non_positive():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["shard", "--xml", "Posts.xml", "--site", "vi", "--shards", "0"])


def test_cmd_download_delegates_to_run_downloader(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "run_downloader", lambda args: calls.append(args))

    args = build_parser().parse_args(["download", "--torrent", "https://x/y.torrent"])
    args.func(args)

    assert len(calls) == 1


def test_cmd_pipeline_builds_pipeline_args_and_runs(monkeypatch):
    captured = {}
    monkeypatch.setattr(cli, "resolve_tables", lambda *, all_tables, tables_csv: ["badges", "posts"])
    monkeypatch.setattr(cli, "run_pipeline", lambda *, pargs, pconn: captured.update(pargs=pargs, pconn=pconn))

    args = build_parser().parse_args(
        ["pipeline", "--site", "vi", "--all", "--shards", "4", "--truncate-first", "--host", "dbhost"]
    )
    cli.cmd_pipeline(args)

    pargs = captured["pargs"]
    assert pargs.site == "vi"
    assert pargs.tables == ["badges", "posts"]
    assert pargs.shards == 4
    assert pargs.truncate_first is True
    assert captured["pconn"].host == "dbhost"


def test_cmd_shard_defaults_out_dir_from_site(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "default_schema_root", lambda: tmp_path / "db" / "schema")
    monkeypatch.setattr(cli, "default_staging_root", lambda: tmp_path / "data" / "staging")
    calls = {}
    monkeypatch.setattr(
        cli,
        "shard_xml",
        lambda *, xml_path, schema_dir, out_dir, cfg: calls.update(
            xml_path=xml_path, schema_dir=schema_dir, out_dir=out_dir, cfg=cfg
        ),
    )

    args = build_parser().parse_args(["shard", "--xml", "Posts.xml", "--site", "vi"])
    cli.cmd_shard(args)

    assert calls["out_dir"] == tmp_path / "data" / "staging" / "vi" / "posts"
    assert calls["schema_dir"] == tmp_path / "db" / "schema" / "posts"


def test_cmd_shard_requires_site_when_out_dir_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "default_schema_root", lambda: tmp_path / "db" / "schema")
    args = build_parser().parse_args(["shard", "--xml", "Posts.xml"])

    with pytest.raises(SystemExit, match="--out-dir is required unless you provide --site"):
        cli.cmd_shard(args)


def test_cmd_shard_uses_explicit_out_dir_over_site_default(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "default_schema_root", lambda: tmp_path / "db" / "schema")
    explicit_out = tmp_path / "custom-out"
    calls = {}
    monkeypatch.setattr(
        cli,
        "shard_xml",
        lambda *, xml_path, schema_dir, out_dir, cfg: calls.update(out_dir=out_dir),
    )

    args = build_parser().parse_args(["shard", "--xml", "Posts.xml", "--out-dir", str(explicit_out)])
    cli.cmd_shard(args)

    assert calls["out_dir"] == explicit_out


def test_cmd_load_applies_ddl_truncates_and_removes_staging_when_requested(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(cli, "ensure_database", lambda conn: calls.append(("ensure_database", conn)))
    monkeypatch.setattr(cli, "ensure_schema", lambda conn: calls.append(("ensure_schema", conn)))
    monkeypatch.setattr(
        cli,
        "load_manifest",
        lambda *, manifest_path, ddl_path, conn, cfg: calls.append(("load_manifest", manifest_path, ddl_path)),
    )
    monkeypatch.setattr(cli, "remove_staging_dir", lambda path: calls.append(("remove_staging_dir", path)))

    manifest_path = tmp_path / "manifest.json"
    args = build_parser().parse_args(["load", "--manifest", str(manifest_path), "--rm-staging"])
    cli.cmd_load(args)

    kinds = [c[0] for c in calls]
    assert kinds == ["ensure_database", "ensure_schema", "load_manifest", "remove_staging_dir"]
    assert calls[3][1] == manifest_path


def test_cmd_load_skips_rm_staging_when_not_requested(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "ensure_database", lambda conn: None)
    monkeypatch.setattr(cli, "ensure_schema", lambda conn: None)
    monkeypatch.setattr(cli, "load_manifest", lambda **k: None)
    calls = []
    monkeypatch.setattr(cli, "remove_staging_dir", lambda path: calls.append(path))

    manifest_path = tmp_path / "manifest.json"
    args = build_parser().parse_args(["load", "--manifest", str(manifest_path)])
    cli.cmd_load(args)

    assert calls == []


def _record_emit_ddl(calls: dict):
    def fake_emit_ddl(schema_dir, out_sql):
        calls["schema_dir"] = schema_dir
        calls["out_sql"] = out_sql
        return out_sql

    return fake_emit_ddl


def test_cmd_ddl_derives_paths_from_table_name(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "default_schema_root", lambda: tmp_path / "db" / "schema")
    monkeypatch.setattr(cli, "default_ddl_root", lambda: tmp_path / "db" / "ddl" / "postgres")
    calls = {}
    monkeypatch.setattr(cli, "emit_ddl", _record_emit_ddl(calls))

    args = build_parser().parse_args(["ddl", "--table", "Posts"])
    cli.cmd_ddl(args)

    assert calls["schema_dir"] == tmp_path / "db" / "schema" / "posts"
    assert calls["out_sql"] == tmp_path / "db" / "ddl" / "postgres" / "create_posts.sql"


def test_cmd_ddl_uses_explicit_schema_dir_and_out_sql(monkeypatch, tmp_path):
    calls = {}
    monkeypatch.setattr(cli, "emit_ddl", _record_emit_ddl(calls))

    schema_dir = tmp_path / "custom-schema"
    out_sql = tmp_path / "custom-out.sql"
    args = build_parser().parse_args(["ddl", "--schema-dir", str(schema_dir), "--out-sql", str(out_sql)])
    cli.cmd_ddl(args)

    assert calls["schema_dir"] == schema_dir
    assert calls["out_sql"] == out_sql


def test_cmd_ddl_requires_both_schema_dir_and_out_sql_without_table():
    args = build_parser().parse_args(["ddl"])
    with pytest.raises(SystemExit, match="Provide --table"):
        cli.cmd_ddl(args)


def test_cmd_ddl_requires_out_sql_when_only_schema_dir_given(tmp_path):
    args = build_parser().parse_args(["ddl", "--schema-dir", str(tmp_path)])
    with pytest.raises(SystemExit, match="Provide --table"):
        cli.cmd_ddl(args)


def test_main_dispatches_to_matching_subcommand(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "emit_ddl", lambda schema_dir, out_sql: calls.append((schema_dir, out_sql)) or out_sql)

    cli.main(["ddl", "--table", "posts"])

    assert len(calls) == 1
