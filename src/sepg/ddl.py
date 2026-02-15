from pathlib import Path

from .schema import Schema


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _parse_decl_pg(decl: str) -> str:
    decl = decl.strip()
    if not decl:
        raise ValueError("Empty type decl")

    return decl.upper()


def generate_ddl(schema: Schema) -> str:
    cols: list[str] = []

    for xml_name in schema.xml_columns:
        decl = schema.xml_types[xml_name]
        cols.append(f"  {_quote_ident(schema.pg_name(xml_name))} {_parse_decl_pg(decl)}")

    if schema.xml_primary_key:
        cols.append(f"  PRIMARY KEY ({_quote_ident(schema.pg_name(schema.xml_primary_key))})")

    body = ",\n".join(cols)
    return f"CREATE TABLE IF NOT EXISTS {_quote_ident(schema.pg_table)} (\n{body}\n);\n"


def emit_ddl(schema_dir: Path, out_sql: Path) -> Path:
    schema = Schema.from_dir(schema_dir)
    sql = generate_ddl(schema)
    out_sql.parent.mkdir(parents=True, exist_ok=True)
    out_sql.write_text(sql, encoding="utf-8")
    return out_sql
