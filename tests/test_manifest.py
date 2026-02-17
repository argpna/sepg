import pytest

from sepg.manifest import Manifest, ManifestPart


def _sample_manifest() -> Manifest:
    return Manifest(
        table="posts",
        primary_key="id",
        columns=["id", "title"],
        source_xml="/data/xml/vi/Posts.xml",
        shards=2,
        parts=[
            ManifestPart(path="shard-00-000001.csv", rows=10, bytes=1234, status="created"),
            ManifestPart(path="shard-01-000001.csv", rows=8, bytes=987, status="created"),
        ],
        total_rows=18,
    )


def test_manifest_round_trips_through_json(tmp_path):
    manifest = _sample_manifest()
    path = tmp_path / "manifest.json"

    manifest.write(path)
    loaded = Manifest.read(path)

    assert loaded == manifest


def test_manifest_from_dict_rejects_absolute_part_path():
    data = {
        "table": "posts",
        "primary_key": "id",
        "columns": ["id"],
        "source_xml": "/data/xml/vi/Posts.xml",
        "shards": 1,
        "parts": [{"path": "/abs/shard-00-000001.csv", "rows": 1, "bytes": 1}],
        "total_rows": 1,
    }
    with pytest.raises(ValueError, match="must be relative"):
        Manifest.from_dict(data)


def test_manifest_from_dict_requires_columns():
    data = {
        "table": "posts",
        "primary_key": "id",
        "columns": [],
        "source_xml": "x",
        "shards": 1,
        "parts": [],
        "total_rows": 0,
    }
    with pytest.raises(ValueError, match="missing columns"):
        Manifest.from_dict(data)


def test_manifest_resolve_part_path_is_relative_to_manifest_dir(tmp_path):
    manifest = _sample_manifest()
    manifest_path = tmp_path / "site" / "posts" / "manifest.json"
    part = manifest.parts[0]

    resolved = manifest.resolve_part_path(manifest_path, part)

    assert resolved == (manifest_path.parent / part.path).resolve()
