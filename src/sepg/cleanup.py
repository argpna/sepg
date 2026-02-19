import shutil
from pathlib import Path


def remove_staging_dir(manifest_path: Path) -> None:
    if manifest_path.name != "manifest.json":
        raise ValueError("Unable to remove staging dir")

    shutil.rmtree(manifest_path.parent)
