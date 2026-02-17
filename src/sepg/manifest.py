import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class ManifestPart:
    path: str
    rows: int | None
    bytes: int | None
    status: str = "created"


@dataclass
class Manifest:
    table: str
    primary_key: str | None
    columns: list[str]
    source_xml: str
    shards: int
    parts: list[ManifestPart]
    total_rows: int
    schema_version: int = 3

    @staticmethod
    def loads(text: str) -> "Manifest":
        data = json.loads(text)
        return Manifest.from_dict(data)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "Manifest":
        table = str(data["table"])
        pk = data.get("primary_key")
        pk = str(pk) if pk is not None else None

        columns = [str(c) for c in (data.get("columns") or [])]
        if not columns:
            raise ValueError("manifest missing columns")

        parts_raw = data.get("parts") or []
        parts: list[ManifestPart] = []
        for p in parts_raw:
            part_path = str(p["path"])

            if Path(part_path).is_absolute():
                raise ValueError(f"manifest part path must be relative, got: {part_path}")

            parts.append(
                ManifestPart(
                    path=part_path,
                    rows=int(p["rows"]) if p.get("rows") is not None else None,
                    bytes=int(p["bytes"]) if p.get("bytes") is not None else None,
                    status=str(p.get("status") or "created"),
                )
            )

        return Manifest(
            table=table,
            primary_key=pk,
            columns=columns,
            source_xml=str(data.get("source_xml") or ""),
            shards=int(data.get("shards") or 0),
            parts=parts,
            total_rows=int(data.get("total_rows") or 0),
            schema_version=int(data.get("schema_version") or 0),
        )

    @staticmethod
    def read(path: Path) -> "Manifest":
        return Manifest.loads(path.read_text(encoding="utf-8"))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def write(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    def resolve_part_path(self, manifest_path: Path, part: ManifestPart) -> Path:
        base = manifest_path.parent
        return (base / part.path).resolve()
