import pytest

from sepg.cleanup import remove_staging_dir


def test_remove_staging_dir_deletes_manifest_parent(tmp_path):
    staging = tmp_path / "site" / "posts"
    staging.mkdir(parents=True)
    manifest_path = staging / "manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    (staging / "shard-00-000001.csv").write_text("id\n", encoding="utf-8")

    remove_staging_dir(manifest_path)

    assert not staging.exists()


def test_remove_staging_dir_rejects_non_manifest_filename(tmp_path):
    other_path = tmp_path / "not-a-manifest.json"
    other_path.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="Unable to remove staging dir"):
        remove_staging_dir(other_path)

    assert other_path.exists()
