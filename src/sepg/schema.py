import re
from dataclasses import dataclass
from pathlib import Path

import yaml


def _pg_ident(name: str) -> str:
    s = str(name).strip()
    if not s:
        raise ValueError("Empty identifier")
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", s)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    return s.lower()


@dataclass(frozen=True)
class Schema:
    xml_table: str
    xml_primary_key: str | None
    xml_columns: list[str]
    xml_types: dict[str, str]

    pg_table: str
    pg_primary_key: str | None
    pg_columns: list[str]

    @staticmethod
    def from_dir(schema_dir: Path) -> "Schema":
        schema_path = schema_dir / "schema.yml"
        if not schema_path.exists():
            raise FileNotFoundError(f"schema.yml not found: {schema_path}")

        data = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"Invalid schema YAML: {schema_path}")

        if "table" not in data:
            raise ValueError(f"Schema missing 'table': {schema_path}")

        xml_table = str(data["table"])
        xml_pk = data.get("primary_key")
        xml_pk = str(xml_pk) if xml_pk else None

        cols = data.get("columns")
        if not isinstance(cols, dict) or not cols:
            raise ValueError(f"Schema missing 'columns': {schema_path}")

        xml_columns = [str(col_name) for col_name in cols.keys()]
        xml_types = {str(col_name): str(type_decl) for col_name, type_decl in cols.items()}

        pg_table = _pg_ident(xml_table)
        pg_pk = _pg_ident(xml_pk) if xml_pk else None
        pg_columns = [_pg_ident(col_name) for col_name in xml_columns]

        return Schema(
            xml_table=xml_table,
            xml_primary_key=xml_pk,
            xml_columns=xml_columns,
            xml_types=xml_types,
            pg_table=pg_table,
            pg_primary_key=pg_pk,
            pg_columns=pg_columns,
        )

    def pg_name(self, xml_name: str) -> str:
        return _pg_ident(xml_name)
