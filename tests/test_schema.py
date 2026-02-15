from pathlib import Path

import pytest

from sepg.schema import Schema, _pg_ident


@pytest.mark.parametrize(
    "xml_name,pg_name",
    [
        ("Id", "id"),
        ("PostTypeId", "post_type_id"),
        ("CreationDate", "creation_date"),
        ("OwnerDisplayName", "owner_display_name"),
        ("ViewCount", "view_count"),
        ("URLName", "url_name"),
    ],
)
def test_pg_ident_converts_camel_case(xml_name, pg_name):
    assert _pg_ident(xml_name) == pg_name


def test_pg_ident_rejects_empty():
    with pytest.raises(ValueError):
        _pg_ident("")


def _write_schema(schema_dir: Path, text: str) -> Path:
    schema_dir.mkdir(parents=True, exist_ok=True)
    path = schema_dir / "schema.yml"
    path.write_text(text, encoding="utf-8")
    return path


def test_schema_from_dir_loads_columns_and_pg_names(tmp_path):
    schema_dir = tmp_path / "posts"
    _write_schema(
        schema_dir,
        """
        table: Posts
        primary_key: Id
        columns:
          Id: integer
          PostTypeId: integer
          CreationDate: timestamp
          Title: varchar(512)
        """,
    )

    schema = Schema.from_dir(schema_dir)

    assert schema.xml_table == "Posts"
    assert schema.pg_table == "posts"
    assert schema.xml_primary_key == "Id"
    assert schema.pg_primary_key == "id"
    assert schema.xml_columns == ["Id", "PostTypeId", "CreationDate", "Title"]
    assert schema.pg_columns == ["id", "post_type_id", "creation_date", "title"]
    assert schema.xml_types["PostTypeId"] == "integer"
    assert schema.pg_name("CreationDate") == "creation_date"


def test_schema_from_dir_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        Schema.from_dir(tmp_path / "does-not-exist")


def test_schema_from_dir_missing_table_key_raises(tmp_path):
    schema_dir = tmp_path / "badges"
    _write_schema(schema_dir, "columns:\n  Id: integer\n")
    with pytest.raises(ValueError, match="missing 'table'"):
        Schema.from_dir(schema_dir)


def test_schema_from_dir_missing_columns_raises(tmp_path):
    schema_dir = tmp_path / "badges"
    _write_schema(schema_dir, "table: Badges\n")
    with pytest.raises(ValueError, match="missing 'columns'"):
        Schema.from_dir(schema_dir)


def test_schema_without_primary_key(tmp_path):
    schema_dir = tmp_path / "tags"
    _write_schema(schema_dir, "table: Tags\ncolumns:\n  Id: integer\n")
    schema = Schema.from_dir(schema_dir)
    assert schema.xml_primary_key is None
    assert schema.pg_primary_key is None
