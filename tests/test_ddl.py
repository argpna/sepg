import pytest

from sepg.ddl import _parse_decl_pg, _quote_ident, emit_ddl, generate_ddl
from sepg.schema import Schema


def _schema(**overrides) -> Schema:
    defaults = dict(
        xml_table="Posts",
        xml_primary_key="Id",
        xml_columns=["Id", "Order"],
        xml_types={"Id": "integer", "Order": "integer"},
        pg_table="posts",
        pg_primary_key="id",
        pg_columns=["id", "order"],
    )
    defaults.update(overrides)
    return Schema(**defaults)


def test_generate_ddl_quotes_table_column_and_primary_key_identifiers():
    ddl = generate_ddl(_schema())

    assert 'CREATE TABLE IF NOT EXISTS "posts" (' in ddl
    assert '"id" INTEGER' in ddl
    assert '"order" INTEGER' in ddl
    assert 'PRIMARY KEY ("id")' in ddl


def test_generate_ddl_without_primary_key_omits_primary_key_clause():
    ddl = generate_ddl(_schema(xml_primary_key=None, pg_primary_key=None))

    assert "PRIMARY KEY" not in ddl


def test_quote_ident_wraps_in_double_quotes():
    assert _quote_ident("posts") == '"posts"'


def test_quote_ident_escapes_embedded_double_quotes():
    assert _quote_ident('weird"name') == '"weird""name"'


def test_parse_decl_pg_strips_whitespace_and_uppercases():
    assert _parse_decl_pg("  varchar(512)  ") == "VARCHAR(512)"


def test_parse_decl_pg_rejects_empty_declaration():
    with pytest.raises(ValueError, match="Empty type decl"):
        _parse_decl_pg("   ")


def test_emit_ddl_writes_file_and_creates_parent_dirs(tmp_path):
    schema_dir = tmp_path / "schema" / "posts"
    schema_dir.mkdir(parents=True)
    (schema_dir / "schema.yml").write_text(
        "table: Posts\nprimary_key: Id\ncolumns:\n  Id: integer\n  Title: varchar(512)\n",
        encoding="utf-8",
    )
    out_sql = tmp_path / "ddl" / "nested" / "create_posts.sql"

    result = emit_ddl(schema_dir, out_sql)

    assert result == out_sql
    assert out_sql.exists()
    text = out_sql.read_text(encoding="utf-8")
    assert 'CREATE TABLE IF NOT EXISTS "posts"' in text
    assert '"id" INTEGER' in text
    assert '"title" VARCHAR(512)' in text
    assert 'PRIMARY KEY ("id")' in text
