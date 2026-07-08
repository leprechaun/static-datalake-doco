from unittest.mock import patch

import deltalake
import polars as pl
import pytest

from datalake_doco.readers.delta import DeltaReader


# ── TableDoc top-level fields ─────────────────────────────────────────────────

def test_name_and_fqn_derived_from_path(numeric_table):
    doc = DeltaReader().read(numeric_table, "mydb/bronze/sales")
    assert doc.name == "sales"
    assert doc.fullyQualifiedName == "mydb.bronze.sales"


def test_uri_matches_input(numeric_table):
    doc = DeltaReader().read(numeric_table, "mydb/bronze/sales")
    assert doc.uri == numeric_table


def test_updated_at_is_set(numeric_table):
    doc = DeltaReader().read(numeric_table, "mydb/bronze/sales")
    assert doc.updatedAt


def test_single_segment_name(numeric_table):
    doc = DeltaReader().read(numeric_table, "events")
    assert doc.name == "events"
    assert doc.fullyQualifiedName == "events"


# ── Column schema ─────────────────────────────────────────────────────────────

def test_column_count(numeric_table):
    doc = DeltaReader().read(numeric_table, "t")
    assert len(doc.columns) == 2
    assert doc.tableProfile.columnCount == 2


def test_column_names(numeric_table):
    doc = DeltaReader().read(numeric_table, "t")
    names = [c.name for c in doc.columns]
    assert names == ["id", "value"]


def test_column_ordinal_positions_are_one_indexed(numeric_table):
    doc = DeltaReader().read(numeric_table, "t")
    positions = [c.ordinalPosition for c in doc.columns]
    assert positions == list(range(1, len(doc.columns) + 1))


def test_int64_maps_to_bigint(numeric_table):
    doc = DeltaReader().read(numeric_table, "t")
    col = next(c for c in doc.columns if c.name == "id")
    assert col.dataType == "BIGINT"


def test_float64_maps_to_double(numeric_table):
    doc = DeltaReader().read(numeric_table, "t")
    col = next(c for c in doc.columns if c.name == "value")
    assert col.dataType == "DOUBLE"


def test_int32_maps_to_int(mixed_table):
    doc = DeltaReader().read(mixed_table, "t")
    col = next(c for c in doc.columns if c.name == "id")
    assert col.dataType == "INT"


def test_string_maps_to_string(mixed_table):
    doc = DeltaReader().read(mixed_table, "t")
    col = next(c for c in doc.columns if c.name == "name")
    assert col.dataType == "STRING"


def test_nullable_field_present(numeric_table):
    doc = DeltaReader().read(numeric_table, "t")
    for col in doc.columns:
        assert isinstance(col.nullable, bool)


# ── Row / column counts ───────────────────────────────────────────────────────

def test_row_count(numeric_table):
    doc = DeltaReader().read(numeric_table, "t")
    assert doc.tableProfile.rowCount == 5


def test_row_count_mixed_table(mixed_table):
    doc = DeltaReader().read(mixed_table, "t")
    assert doc.tableProfile.rowCount == 3


# ── Column profiles ───────────────────────────────────────────────────────────

def test_column_profile_names_match_columns(mixed_table):
    doc = DeltaReader().read(mixed_table, "t")
    profile_names = {p.name for p in doc.tableProfile.columnProfile}
    column_names = {c.name for c in doc.columns}
    assert profile_names == column_names


def test_numeric_column_profile_has_mean(mixed_table):
    doc = DeltaReader().read(mixed_table, "t")
    by_name = {p.name: p for p in doc.tableProfile.columnProfile}
    assert by_name["score"].mean == pytest.approx(2.5)
    assert by_name["score"].min == 1.5
    assert by_name["score"].max == 3.5


def test_string_column_profile_has_top_value(mixed_table):
    doc = DeltaReader().read(mixed_table, "t")
    by_name = {p.name: p for p in doc.tableProfile.columnProfile}
    assert by_name["name"].top == "alice"
    assert by_name["name"].freq == 2
    assert by_name["name"].uniqueCount == 2


def test_string_column_profile_has_no_mean(mixed_table):
    doc = DeltaReader().read(mixed_table, "t")
    by_name = {p.name: p for p in doc.tableProfile.columnProfile}
    assert by_name["name"].mean is None


def test_null_counts_in_profile(nullable_table):
    doc = DeltaReader().read(nullable_table, "t")
    by_name = {p.name: p for p in doc.tableProfile.columnProfile}
    assert by_name["x"].nullCount == 1.0
    assert by_name["label"].nullCount == 1.0


# ── Sample data ───────────────────────────────────────────────────────────────

def test_no_sample_data_by_default(numeric_table):
    doc = DeltaReader().read(numeric_table, "t", sample_count=0)
    assert doc.sampleData is None


def test_sample_data_column_names(numeric_table):
    doc = DeltaReader().read(numeric_table, "t", sample_count=3)
    assert doc.sampleData.columns == ["id", "value"]


def test_sample_data_row_count(numeric_table):
    doc = DeltaReader().read(numeric_table, "t", sample_count=3)
    assert len(doc.sampleData.rows) == 3


def test_sample_data_row_width(numeric_table):
    doc = DeltaReader().read(numeric_table, "t", sample_count=3)
    for row in doc.sampleData.rows:
        assert len(row) == 2


def test_sample_data_respects_limit(numeric_table):
    doc = DeltaReader().read(numeric_table, "t", sample_count=2)
    assert len(doc.sampleData.rows) == 2


def test_sample_data_values_are_json_safe_types(mixed_table):
    doc = DeltaReader().read(mixed_table, "t", sample_count=3)
    for row in doc.sampleData.rows:
        for cell in row:
            assert isinstance(cell, (str, int, float, bool, type(None)))


# ── Delta history ─────────────────────────────────────────────────────────────

def test_history_present(numeric_table):
    doc = DeltaReader().read(numeric_table, "t")
    assert doc.extension is not None
    assert "deltaHistory" in doc.extension
    assert len(doc.extension["deltaHistory"]) >= 1


def test_history_entry_fields(numeric_table):
    doc = DeltaReader().read(numeric_table, "t")
    entry = doc.extension["deltaHistory"][0]
    assert entry.version is not None
    assert entry.timestamp
    assert entry.operation


def test_history_limit(tmp_path):
    path = str(tmp_path / "t")
    df = pl.DataFrame({"x": pl.Series([1], dtype=pl.Int64)})
    deltalake.write_deltalake(path, df)
    deltalake.write_deltalake(path, df, mode="append")  # creates a second commit

    doc_all = DeltaReader().read(path, "t")
    doc_limited = DeltaReader().read(path, "t", history_limit=1)
    assert len(doc_all.extension["deltaHistory"]) == 2
    assert len(doc_limited.extension["deltaHistory"]) == 1


def test_extension_is_none_when_history_is_empty(numeric_table):
    with patch.object(deltalake.DeltaTable, "history", return_value=[]):
        doc = DeltaReader().read(numeric_table, "t")
    assert doc.extension is None
