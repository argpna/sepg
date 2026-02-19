from pathlib import Path

from sepg.shard import ShardConfig, _iter_xml_row_range, shard_xml


def _write_xml(path: Path, rows: list[str]) -> None:
    lines = ['<?xml version="1.0" encoding="utf-8"?>', "<posts>"]
    lines.extend(rows)
    lines.append("</posts>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_iter_xml_row_range_maps_known_columns_by_name(tmp_path):
    xml_path = tmp_path / "Posts.xml"
    _write_xml(
        xml_path,
        [
            '  <row Id="1" PostTypeId="2" Title="Hello" />',
            '  <row Id="2" Title="No type" />',
        ],
    )
    xml_cols = ["Id", "PostTypeId", "Title"]

    rows = list(_iter_xml_row_range(xml_path, start=0, end=xml_path.stat().st_size, xml_cols=xml_cols))

    assert rows == [
        ["1", "2", "Hello"],
        ["2", None, "No type"],
    ]


def test_iter_xml_row_range_unescapes_html_entities(tmp_path):
    xml_path = tmp_path / "Posts.xml"
    _write_xml(xml_path, ['  <row Id="1" Title="Cats &amp; Dogs: &quot;Best&quot;" />'])
    xml_cols = ["Id", "Title"]

    rows = list(_iter_xml_row_range(xml_path, start=0, end=xml_path.stat().st_size, xml_cols=xml_cols))

    assert rows == [["1", 'Cats & Dogs: "Best"']]


def test_iter_xml_row_range_ignores_unmapped_attributes(tmp_path):
    xml_path = tmp_path / "Posts.xml"
    _write_xml(xml_path, ['  <row Id="1" SomeUnknownAttr="ignored" Title="kept" />'])
    xml_cols = ["Id", "Title"]

    rows = list(_iter_xml_row_range(xml_path, start=0, end=xml_path.stat().st_size, xml_cols=xml_cols))

    assert rows == [["1", "kept"]]


def test_iter_xml_row_range_skips_partial_first_line_on_offset_start(tmp_path):
    xml_path = tmp_path / "Posts.xml"
    row_lines = [
        '  <row Id="1" Title="first" />',
        '  <row Id="2" Title="second" />',
        '  <row Id="3" Title="third" />',
    ]
    _write_xml(xml_path, row_lines)
    xml_cols = ["Id", "Title"]

    full_text = xml_path.read_text(encoding="utf-8")
    header_len = len(full_text.split("\n")[0]) + 1 + len(full_text.split("\n")[1]) + 1
    mid_first_row = header_len + 5  # lands inside the first <row .../> line, not on a boundary

    rows = list(
        _iter_xml_row_range(xml_path, start=mid_first_row, end=len(full_text.encode("utf-8")), xml_cols=xml_cols)
    )

    # starting mid-way through row 1's line must skip the rest of that line entirely
    assert rows == [["2", "second"], ["3", "third"]]


def test_iter_xml_row_range_warns_when_row_tag_has_no_attributes_on_its_line(tmp_path, monkeypatch):
    warnings = []
    monkeypatch.setattr("sepg.shard.warn", warnings.append)

    xml_path = tmp_path / "Posts.xml"
    _write_xml(
        xml_path,
        [
            '  <row Id="1" Title="ok" />',
            "  <row",  # attributes wrap to the next line - violates the one-line-per-row contract
            '    Id="2" Title="wraps" />',
        ],
    )
    xml_cols = ["Id", "Title"]

    rows = list(_iter_xml_row_range(xml_path, start=0, end=xml_path.stat().st_size, xml_cols=xml_cols))

    assert rows == [["1", "ok"]]  # the wrapped row is silently skipped, not parsed
    assert len(warnings) == 1
    assert "found 2 '<row' line(s) but only parsed 1" in warnings[0]


def test_iter_xml_row_range_no_warning_when_every_row_tag_line_parses(tmp_path, monkeypatch):
    warnings = []
    monkeypatch.setattr("sepg.shard.warn", warnings.append)

    xml_path = tmp_path / "Posts.xml"
    _write_xml(xml_path, ['  <row Id="1" Title="ok" />', '  <row Id="2" Title="also ok" />'])
    xml_cols = ["Id", "Title"]

    list(_iter_xml_row_range(xml_path, start=0, end=xml_path.stat().st_size, xml_cols=xml_cols))

    assert warnings == []


def test_shard_xml_routes_rows_by_id_modulo_shard_count(tmp_path):
    schema_dir = tmp_path / "schema" / "posts"
    schema_dir.mkdir(parents=True)
    (schema_dir / "schema.yml").write_text(
        "table: Posts\nprimary_key: Id\ncolumns:\n  Id: integer\n  Title: varchar(512)\n",
        encoding="utf-8",
    )

    xml_path = tmp_path / "Posts.xml"
    _write_xml(
        xml_path,
        [f'  <row Id="{i}" Title="post {i}" />' for i in range(1, 7)],
    )

    out_dir = tmp_path / "staging"
    manifest_path = shard_xml(
        xml_path=xml_path,
        schema_dir=schema_dir,
        out_dir=out_dir,
        cfg=ShardConfig(shards=2, shard_workers=1, max_rows_per_part=100),
    )

    from sepg.manifest import Manifest

    manifest = Manifest.read(manifest_path)
    assert manifest.total_rows == 6
    assert manifest.table == "posts"

    all_rows = []
    for part in manifest.parts:
        part_path = out_dir / part.path
        lines = part_path.read_text(encoding="utf-8").splitlines()
        assert lines[0] == "id,title"  # header
        all_rows.extend(lines[1:])

    assert len(all_rows) == 6
    # every even Id (2,4,6) -> shard 0, every odd Id (1,3,5) -> shard 1
    even_shard_file = out_dir / [p.path for p in manifest.parts if p.path.startswith("shard-00")][0]
    odd_shard_file = out_dir / [p.path for p in manifest.parts if p.path.startswith("shard-01")][0]
    assert {line.split(",")[0] for line in even_shard_file.read_text().splitlines()[1:]} == {
        "2",
        "4",
        "6",
    }
    assert {line.split(",")[0] for line in odd_shard_file.read_text().splitlines()[1:]} == {
        "1",
        "3",
        "5",
    }
