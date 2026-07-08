import json

import deltalake
import polars as pl
import pytest

from datalake_doco.models import Catalog, CatalogEntry
from datalake_doco.readers.delta import DeltaReader
from datalake_doco.writer import write_output


@pytest.fixture
def simple_doc(tmp_path):
    path = str(tmp_path / "src" / "bronze" / "events")
    (tmp_path / "src" / "bronze" / "events").mkdir(parents=True)
    deltalake.write_deltalake(
        path,
        pl.DataFrame({"id": pl.Series([1, 2, 3], dtype=pl.Int64)}),
    )
    return DeltaReader().read(path, "src/bronze/events")


def _catalog(doc):
    return Catalog(
        generatedAt="2026-01-01T00:00:00+00:00",
        sources=["file:///data"],
        tables=[
            CatalogEntry(
                fullyQualifiedName=doc.fullyQualifiedName,
                name=doc.name,
                uri=doc.uri,
                docPath=f"tables/{doc.fullyQualifiedName.replace('.', '/')}.json",
                updatedAt=doc.updatedAt,
                rowCount=doc.tableProfile.rowCount,
                columnCount=doc.tableProfile.columnCount,
            )
        ],
    )


# ── catalog.json ──────────────────────────────────────────────────────────────

def test_catalog_json_is_created(simple_doc, tmp_path):
    out = tmp_path / "out"
    write_output(_catalog(simple_doc), [simple_doc], out)
    assert (out / "catalog.json").exists()


def test_catalog_json_top_level_keys(simple_doc, tmp_path):
    out = tmp_path / "out"
    write_output(_catalog(simple_doc), [simple_doc], out)
    data = json.loads((out / "catalog.json").read_text())
    assert "generatedAt" in data
    assert "sources" in data
    assert "tables" in data


def test_catalog_json_generated_at(simple_doc, tmp_path):
    out = tmp_path / "out"
    write_output(_catalog(simple_doc), [simple_doc], out)
    data = json.loads((out / "catalog.json").read_text())
    assert data["generatedAt"] == "2026-01-01T00:00:00+00:00"


def test_catalog_json_sources(simple_doc, tmp_path):
    out = tmp_path / "out"
    write_output(_catalog(simple_doc), [simple_doc], out)
    data = json.loads((out / "catalog.json").read_text())
    assert data["sources"] == ["file:///data"]


def test_catalog_entry_fields(simple_doc, tmp_path):
    out = tmp_path / "out"
    write_output(_catalog(simple_doc), [simple_doc], out)
    data = json.loads((out / "catalog.json").read_text())
    entry = data["tables"][0]
    assert entry["fullyQualifiedName"] == "src.bronze.events"
    assert entry["name"] == "events"
    assert entry["rowCount"] == 3
    assert entry["columnCount"] == 1
    assert "docPath" in entry
    assert "updatedAt" in entry


# ── Per-table JSON ────────────────────────────────────────────────────────────

def test_table_doc_file_is_created(simple_doc, tmp_path):
    out = tmp_path / "out"
    write_output(_catalog(simple_doc), [simple_doc], out)
    assert (out / "tables" / "src" / "bronze" / "events.json").exists()


def test_table_doc_top_level_keys(simple_doc, tmp_path):
    out = tmp_path / "out"
    write_output(_catalog(simple_doc), [simple_doc], out)
    data = json.loads((out / "tables" / "src" / "bronze" / "events.json").read_text())
    for key in ("name", "fullyQualifiedName", "uri", "updatedAt", "columns", "tableProfile"):
        assert key in data, f"missing key: {key}"


def test_table_doc_name_and_fqn(simple_doc, tmp_path):
    out = tmp_path / "out"
    write_output(_catalog(simple_doc), [simple_doc], out)
    data = json.loads((out / "tables" / "src" / "bronze" / "events.json").read_text())
    assert data["name"] == "events"
    assert data["fullyQualifiedName"] == "src.bronze.events"


def test_table_doc_columns(simple_doc, tmp_path):
    out = tmp_path / "out"
    write_output(_catalog(simple_doc), [simple_doc], out)
    data = json.loads((out / "tables" / "src" / "bronze" / "events.json").read_text())
    assert len(data["columns"]) == 1
    col = data["columns"][0]
    assert col["name"] == "id"
    assert col["dataType"] == "BIGINT"
    assert "nullable" in col
    assert col["ordinalPosition"] == 1


def test_table_profile_fields(simple_doc, tmp_path):
    out = tmp_path / "out"
    write_output(_catalog(simple_doc), [simple_doc], out)
    data = json.loads((out / "tables" / "src" / "bronze" / "events.json").read_text())
    profile = data["tableProfile"]
    assert profile["rowCount"] == 3
    assert profile["columnCount"] == 1
    assert "columnProfile" in profile
    assert "timestamp" in profile


def test_column_profile_fields(simple_doc, tmp_path):
    out = tmp_path / "out"
    write_output(_catalog(simple_doc), [simple_doc], out)
    data = json.loads((out / "tables" / "src" / "bronze" / "events.json").read_text())
    col_profile = data["tableProfile"]["columnProfile"][0]
    assert col_profile["name"] == "id"
    assert "valuesCount" in col_profile
    assert "nullCount" in col_profile


# ── JSON safety ───────────────────────────────────────────────────────────────

def test_no_nan_or_inf_in_output(tmp_path):
    path = str(tmp_path / "all_nulls")
    (tmp_path / "all_nulls").mkdir()
    deltalake.write_deltalake(
        path,
        pl.DataFrame({"x": pl.Series([None, None], dtype=pl.Float64)}),
    )
    doc = DeltaReader().read(path, "all_nulls")
    catalog = Catalog(generatedAt="t", sources=[], tables=[])
    out = tmp_path / "out"
    write_output(catalog, [doc], out)

    for f in out.rglob("*.json"):
        text = f.read_text()
        assert "NaN" not in text, f"NaN in {f}"
        assert "Infinity" not in text, f"Infinity in {f}"
        json.loads(text)  # must be valid JSON


# ── Idempotency ───────────────────────────────────────────────────────────────

def test_second_run_replaces_tables_dir(simple_doc, tmp_path):
    out = tmp_path / "out"
    write_output(_catalog(simple_doc), [simple_doc], out)
    write_output(_catalog(simple_doc), [simple_doc], out)
    table_files = list((out / "tables").rglob("*.json"))
    assert len(table_files) == 1
