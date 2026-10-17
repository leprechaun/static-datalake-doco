import json

import pytest
from conftest import FIXED_TS

from datalake_doco.models import (
    Catalog,
    CatalogEntry,
    Column,
    ColumnProfile,
    TableDoc,
    TableProfile,
)
from datalake_doco.writer import write_output


def make_column(name="id", data_type="BIGINT", nullable=True, ordinal=1, partitioned=False):
    return Column(name=name, dataType=data_type, nullable=nullable, ordinalPosition=ordinal, partitioned=partitioned)


def make_profile(name="id", **kwargs):
    defaults = {"timestamp": FIXED_TS, "valuesCount": 3.0, "nullCount": 0.0}
    defaults.update(kwargs)
    return ColumnProfile(name=name, **defaults)


def make_table_doc(**overrides):
    col = make_column()
    doc = TableDoc(
        name="events",
        fullyQualifiedName="src.bronze.events",
        uri="/fake/src/bronze/events",
        updatedAt=FIXED_TS,
        columns=[col],
        tableProfile=TableProfile(
            timestamp=FIXED_TS,
            rowCount=3,
            columnCount=1,
            columnProfile=[make_profile()],
        ),
    )
    for k, v in overrides.items():
        setattr(doc, k, v)
    return doc


def make_catalog_entry(doc):
    return CatalogEntry(
        fullyQualifiedName=doc.fullyQualifiedName,
        name=doc.name,
        uri=doc.uri,
        docPath=f"tables/{doc.fullyQualifiedName.replace('.', '/')}.json",
        updatedAt=doc.updatedAt,
        rowCount=doc.tableProfile.rowCount,
        columnCount=doc.tableProfile.columnCount,
    )


@pytest.fixture
def simple_doc():
    return make_table_doc()


@pytest.fixture
def simple_catalog(simple_doc):
    return Catalog(
        generatedAt=FIXED_TS,
        sources=["/fake/data"],
        tables=[make_catalog_entry(simple_doc)],
    )


# ── catalog.json ──────────────────────────────────────────────────────────────

def test_catalog_json_created(simple_doc, simple_catalog, tmp_path):
    out = tmp_path / "out"
    write_output(simple_catalog, [simple_doc], out)
    assert (out / "catalog.json").exists()


def test_catalog_json_top_level_keys(simple_doc, simple_catalog, tmp_path):
    out = tmp_path / "out"
    write_output(simple_catalog, [simple_doc], out)
    data = json.loads((out / "catalog.json").read_text())
    assert "generatedAt" in data
    assert "sources" in data
    assert "tables" in data


def test_catalog_entry_shape(simple_doc, simple_catalog, tmp_path):
    out = tmp_path / "out"
    write_output(simple_catalog, [simple_doc], out)
    entry = json.loads((out / "catalog.json").read_text())["tables"][0]
    assert entry["fullyQualifiedName"] == "src.bronze.events"
    assert entry["name"] == "events"
    assert entry["rowCount"] == 3
    assert entry["columnCount"] == 1
    assert entry["docPath"] == "tables/src/bronze/events.json"


# ── Per-table JSON ────────────────────────────────────────────────────────────

def test_table_doc_file_created(simple_doc, simple_catalog, tmp_path):
    out = tmp_path / "out"
    write_output(simple_catalog, [simple_doc], out)
    assert (out / "tables" / "src" / "bronze" / "events.json").exists()


def test_table_doc_top_level_keys(simple_doc, simple_catalog, tmp_path):
    out = tmp_path / "out"
    write_output(simple_catalog, [simple_doc], out)
    data = json.loads((out / "tables" / "src" / "bronze" / "events.json").read_text())
    for key in ("name", "fullyQualifiedName", "uri", "updatedAt", "columns", "tableProfile", "partitionColumns"):
        assert key in data, f"missing key: {key}"


def test_table_doc_column_shape(simple_doc, simple_catalog, tmp_path):
    out = tmp_path / "out"
    write_output(simple_catalog, [simple_doc], out)
    col = json.loads((out / "tables" / "src" / "bronze" / "events.json").read_text())["columns"][0]
    assert col["name"] == "id"
    assert col["dataType"] == "BIGINT"
    assert col["nullable"] is True
    assert col["ordinalPosition"] == 1
    assert col["partitioned"] is False


def test_table_profile_shape(simple_doc, simple_catalog, tmp_path):
    out = tmp_path / "out"
    write_output(simple_catalog, [simple_doc], out)
    profile = json.loads((out / "tables" / "src" / "bronze" / "events.json").read_text())["tableProfile"]
    assert profile["rowCount"] == 3
    assert profile["columnCount"] == 1
    assert len(profile["columnProfile"]) == 1


# ── Float safety ──────────────────────────────────────────────────────────────

def test_nan_in_stats_becomes_null_in_json(tmp_path):
    doc = make_table_doc(
        tableProfile=TableProfile(
            timestamp=FIXED_TS,
            rowCount=3,
            columnCount=1,
            columnProfile=[make_profile(mean=float("nan"), stddev=float("inf"))],
        )
    )
    catalog = Catalog(generatedAt=FIXED_TS, sources=[], tables=[])
    out = tmp_path / "out"
    write_output(catalog, [doc], out)
    text = (out / "tables" / "src" / "bronze" / "events.json").read_text()
    assert "NaN" not in text
    assert "Infinity" not in text
    data = json.loads(text)
    assert data["tableProfile"]["columnProfile"][0]["mean"] is None
    assert data["tableProfile"]["columnProfile"][0]["stddev"] is None


# ── Partitioning in JSON ──────────────────────────────────────────────────────

def test_unpartitioned_table_has_empty_partition_columns_in_json(simple_doc, simple_catalog, tmp_path):
    out = tmp_path / "out"
    write_output(simple_catalog, [simple_doc], out)
    data = json.loads((out / "tables" / "src" / "bronze" / "events.json").read_text())
    assert data["partitionColumns"] == []


def test_partitioned_table_serialises_partition_columns(tmp_path):
    doc = make_table_doc(
        columns=[
            make_column("id", ordinal=1),
            make_column("region", data_type="STRING", ordinal=2, partitioned=True),
        ],
        tableProfile=TableProfile(
            timestamp=FIXED_TS, rowCount=4, columnCount=2,
            columnProfile=[make_profile("id"), make_profile("region")],
        ),
        partitionColumns=["region"],
    )
    catalog = Catalog(generatedAt=FIXED_TS, sources=[], tables=[])
    out = tmp_path / "out"
    write_output(catalog, [doc], out)
    data = json.loads((out / "tables" / "src" / "bronze" / "events.json").read_text())
    assert data["partitionColumns"] == ["region"]
    by_name = {c["name"]: c for c in data["columns"]}
    assert by_name["region"]["partitioned"] is True
    assert by_name["id"]["partitioned"] is False


# ── Idempotency ───────────────────────────────────────────────────────────────

def test_second_run_replaces_tables_dir(simple_doc, simple_catalog, tmp_path):
    out = tmp_path / "out"
    write_output(simple_catalog, [simple_doc], out)
    write_output(simple_catalog, [simple_doc], out)
    assert len(list((out / "tables").rglob("*.json"))) == 1
