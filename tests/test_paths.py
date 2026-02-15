from pathlib import Path

import pytest

from sepg import paths


def test_project_root_uses_sepg_root_env_var(tmp_path, monkeypatch):
    monkeypatch.setenv("SEPG_ROOT", str(tmp_path))
    assert paths.project_root() == tmp_path.resolve()


def test_project_root_expands_user_in_sepg_root(monkeypatch):
    monkeypatch.setenv("SEPG_ROOT", "~")
    assert paths.project_root() == Path.home().resolve()


def test_project_root_falls_back_to_repo_root_without_env_var(monkeypatch):
    monkeypatch.delenv("SEPG_ROOT", raising=False)
    root = paths.project_root()
    assert (root / "src" / "sepg" / "paths.py").exists()


def test_data_and_db_dirs_are_relative_to_project_root(tmp_path, monkeypatch):
    monkeypatch.setenv("SEPG_ROOT", str(tmp_path))
    assert paths.data_dir() == tmp_path / "data"
    assert paths.xml_dir() == tmp_path / "data" / "xml"
    assert paths.staging_dir() == tmp_path / "data" / "staging"
    assert paths.db_dir() == tmp_path / "db"
    assert paths.schema_dir() == tmp_path / "db" / "schema"
    assert paths.ddl_dir() == tmp_path / "db" / "ddl" / "postgres"


def test_list_schema_tables_raises_when_schema_dir_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("SEPG_ROOT", str(tmp_path))
    with pytest.raises(FileNotFoundError):
        paths.list_schema_tables()


def test_list_schema_tables_returns_sorted_directory_names_only(tmp_path, monkeypatch):
    monkeypatch.setenv("SEPG_ROOT", str(tmp_path))
    schema_root = tmp_path / "db" / "schema"
    for name in ["votes", "badges", "posts"]:
        (schema_root / name).mkdir(parents=True)
    (schema_root / "README.md").write_text("not a table", encoding="utf-8")

    assert paths.list_schema_tables() == ["badges", "posts", "votes"]


@pytest.mark.parametrize(
    "table,expected_filename",
    [
        ("badges", "Badges.xml"),
        ("post_history", "PostHistory.xml"),
        ("post_links", "PostLinks.xml"),
        ("BADGES", "Badges.xml"),
        ("tags", "Tags.xml"),
        ("unknown_table", "Unknown_table.xml"),
    ],
)
def test_pick_xml_path_maps_table_name_to_xml_filename(tmp_path, monkeypatch, table, expected_filename):
    monkeypatch.setenv("SEPG_ROOT", str(tmp_path))
    site_dir = tmp_path / "data" / "xml" / "vi"
    site_dir.mkdir(parents=True)
    (site_dir / expected_filename).write_text("<rows/>", encoding="utf-8")

    assert paths.pick_xml_path("vi", table) == site_dir / expected_filename


def test_pick_xml_path_raises_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("SEPG_ROOT", str(tmp_path))
    with pytest.raises(FileNotFoundError):
        paths.pick_xml_path("vi", "posts")
