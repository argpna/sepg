import os
from pathlib import Path

XML_TITLE_MAP: dict[str, str] = {
    "badges": "Badges",
    "comments": "Comments",
    "post_history": "PostHistory",
    "post_links": "PostLinks",
    "posts": "Posts",
    "tags": "Tags",
    "users": "Users",
    "votes": "Votes",
}


def project_root() -> Path:
    v = os.getenv("SEPG_ROOT")
    if v:
        return Path(v).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    return project_root() / "data"


def xml_dir() -> Path:
    return data_dir() / "xml"


def staging_dir() -> Path:
    return data_dir() / "staging"


def db_dir() -> Path:
    return project_root() / "db"


def schema_dir() -> Path:
    return db_dir() / "schema"


def ddl_dir() -> Path:
    return db_dir() / "ddl" / "postgres"


def list_schema_tables() -> list[str]:
    root = schema_dir()
    if not root.exists():
        raise FileNotFoundError(f"schema dir not found: {root}")
    return sorted(p.name for p in root.iterdir() if p.is_dir())


def _xml_filename(table: str) -> str:
    name = XML_TITLE_MAP.get(table.lower(), table.capitalize())
    return f"{name}.xml"


def xml_path_for(site: str, table: str) -> Path:
    return xml_dir() / site / _xml_filename(table)


def pick_xml_path(site: str, table: str) -> Path:
    path = xml_path_for(site, table)
    if not path.exists():
        raise FileNotFoundError(f"XML not found: {path}")
    return path
