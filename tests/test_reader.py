from contextlib import contextmanager
from unittest.mock import patch

import polars as pl
import pytest

from conftest import FIXED_TS, make_field, make_mock_dt
from datalake_doco.readers.delta import DeltaReader


@contextmanager
def _read_ctx(df, fields=None, partition_columns=None, history=None):
    """Patch DeltaTable and pl.read_delta for the duration of the with block."""
    mock_dt = make_mock_dt(
        fields if fields is not None else [make_field(c) for c in df.columns],
        partition_columns=partition_columns,
        history=history,
    )
    with patch("datalake_doco.readers.delta.deltalake.DeltaTable", return_value=mock_dt), \
         patch("datalake_doco.readers.delta.pl.scan_delta", return_value=df.lazy()):
        yield


# ── Identity fields ───────────────────────────────────────────────────────────

def test_name_and_fqn_derived_from_path():
    df = pl.DataFrame({"id": pl.Series([1], dtype=pl.Int64)})
    with _read_ctx(df):
        doc = DeltaReader().read("/fake/path", "mydb/bronze/events")
    assert doc.name == "events"
    assert doc.fullyQualifiedName == "mydb.bronze.events"


def test_single_segment_name():
    df = pl.DataFrame({"id": pl.Series([1], dtype=pl.Int64)})
    with _read_ctx(df):
        doc = DeltaReader().read("/fake/path", "events")
    assert doc.name == "events"
    assert doc.fullyQualifiedName == "events"


def test_uri_passed_through():
    df = pl.DataFrame({"id": pl.Series([1], dtype=pl.Int64)})
    with _read_ctx(df):
        doc = DeltaReader().read("/my/table/path", "t")
    assert doc.uri == "/my/table/path"


def test_updated_at_is_set():
    df = pl.DataFrame({"id": pl.Series([1], dtype=pl.Int64)})
    with _read_ctx(df):
        doc = DeltaReader().read("/fake/path", "t")
    assert doc.updatedAt


# ── Column schema ─────────────────────────────────────────────────────────────

def test_column_count():
    df = pl.DataFrame({"a": pl.Series([1], dtype=pl.Int64), "b": pl.Series([1.0], dtype=pl.Float64)})
    with _read_ctx(df):
        doc = DeltaReader().read("/fake/path", "t")
    assert len(doc.columns) == 2
    assert doc.tableProfile.columnCount == 2


def test_column_names_in_schema_order():
    df = pl.DataFrame({"id": pl.Series([1], dtype=pl.Int64), "name": pl.Series(["a"], dtype=pl.String)})
    with _read_ctx(df):
        doc = DeltaReader().read("/fake/path", "t")
    assert [c.name for c in doc.columns] == ["id", "name"]


def test_ordinal_positions_are_one_indexed():
    df = pl.DataFrame({"a": pl.Series([1], dtype=pl.Int64), "b": pl.Series([2], dtype=pl.Int64)})
    with _read_ctx(df):
        doc = DeltaReader().read("/fake/path", "t")
    assert [c.ordinalPosition for c in doc.columns] == [1, 2]


def test_nullable_read_from_delta_schema():
    df = pl.DataFrame({"id": pl.Series([1], dtype=pl.Int64)})
    fields = [make_field("id", nullable=False)]
    with _read_ctx(df, fields=fields):
        doc = DeltaReader().read("/fake/path", "t")
    assert doc.columns[0].nullable is False


def test_datatype_mapped_from_polars_dtype():
    df = pl.DataFrame({
        "i": pl.Series([1], dtype=pl.Int64),
        "s": pl.Series(["a"], dtype=pl.String),
        "f": pl.Series([1.0], dtype=pl.Float64),
    })
    with _read_ctx(df):
        doc = DeltaReader().read("/fake/path", "t")
    by_name = {c.name: c for c in doc.columns}
    assert by_name["i"].dataType == "BIGINT"
    assert by_name["s"].dataType == "STRING"
    assert by_name["f"].dataType == "DOUBLE"


# ── Table profile ─────────────────────────────────────────────────────────────

def test_row_count():
    df = pl.DataFrame({"x": pl.Series([1, 2, 3, 4, 5], dtype=pl.Int64)})
    with _read_ctx(df):
        doc = DeltaReader().read("/fake/path", "t")
    assert doc.tableProfile.rowCount == 5


def test_column_profiles_cover_all_columns():
    df = pl.DataFrame({"a": pl.Series([1], dtype=pl.Int64), "b": pl.Series(["x"], dtype=pl.String)})
    with _read_ctx(df):
        doc = DeltaReader().read("/fake/path", "t")
    assert {p.name for p in doc.tableProfile.columnProfile} == {"a", "b"}


def test_numeric_column_has_mean_in_profile():
    df = pl.DataFrame({"x": pl.Series([1.0, 2.0, 3.0], dtype=pl.Float64)})
    with _read_ctx(df):
        doc = DeltaReader().read("/fake/path", "t")
    profile = doc.tableProfile.columnProfile[0]
    assert profile.mean == pytest.approx(2.0)


def test_string_column_has_top_in_profile():
    df = pl.DataFrame({"s": pl.Series(["a", "b", "a"], dtype=pl.String)})
    with _read_ctx(df):
        doc = DeltaReader().read("/fake/path", "t")
    profile = doc.tableProfile.columnProfile[0]
    assert profile.top == "a"
    assert profile.freq == 2


def test_null_count_in_profile():
    df = pl.DataFrame({"x": pl.Series([1.0, None, 3.0], dtype=pl.Float64)})
    with _read_ctx(df):
        doc = DeltaReader().read("/fake/path", "t")
    assert doc.tableProfile.columnProfile[0].nullCount == 1.0


# ── Sample data ───────────────────────────────────────────────────────────────

def test_no_sample_data_by_default():
    df = pl.DataFrame({"x": pl.Series([1, 2, 3], dtype=pl.Int64)})
    with _read_ctx(df):
        doc = DeltaReader().read("/fake/path", "t", sample_count=0)
    assert doc.sampleData is None


def test_sample_data_shape():
    df = pl.DataFrame({"x": pl.Series([1, 2, 3, 4, 5], dtype=pl.Int64)})
    with _read_ctx(df):
        doc = DeltaReader().read("/fake/path", "t", sample_count=3)
    assert doc.sampleData.columns == ["x"]
    assert len(doc.sampleData.rows) == 3


def test_sample_data_values_are_json_safe():
    df = pl.DataFrame({"x": pl.Series([1, 2, 3], dtype=pl.Int64)})
    with _read_ctx(df):
        doc = DeltaReader().read("/fake/path", "t", sample_count=3)
    for row in doc.sampleData.rows:
        for cell in row:
            assert isinstance(cell, (str, int, float, bool, type(None)))


# ── History ───────────────────────────────────────────────────────────────────

def test_history_present():
    df = pl.DataFrame({"x": pl.Series([1], dtype=pl.Int64)})
    with _read_ctx(df):
        doc = DeltaReader().read("/fake/path", "t")
    assert doc.extension is not None
    assert len(doc.extension["deltaHistory"]) == 1
    entry = doc.extension["deltaHistory"][0]
    assert entry.version == 0
    assert entry.operation == "WRITE"
    assert entry.timestamp  # non-empty string


def test_history_limit():
    history = [
        {"version": 1, "timestamp": 1704067200000, "operation": "WRITE", "operationParameters": {}},
        {"version": 0, "timestamp": 1704067200000, "operation": "CREATE", "operationParameters": {}},
    ]
    df = pl.DataFrame({"x": pl.Series([1], dtype=pl.Int64)})
    with _read_ctx(df, history=history):
        doc_full = DeltaReader().read("/fake/path", "t")
    with _read_ctx(df, history=history[:1]):
        doc_limited = DeltaReader().read("/fake/path", "t", history_limit=1)
    assert len(doc_full.extension["deltaHistory"]) == 2
    assert len(doc_limited.extension["deltaHistory"]) == 1


def test_extension_is_none_when_history_empty():
    df = pl.DataFrame({"x": pl.Series([1], dtype=pl.Int64)})
    with _read_ctx(df, history=[]):
        doc = DeltaReader().read("/fake/path", "t")
    assert doc.extension is None


# ── Partitioning ──────────────────────────────────────────────────────────────

def test_unpartitioned_table_has_empty_partition_columns():
    df = pl.DataFrame({"id": pl.Series([1], dtype=pl.Int64)})
    with _read_ctx(df, partition_columns=[]):
        doc = DeltaReader().read("/fake/path", "t")
    assert doc.partitionColumns == []


def test_unpartitioned_columns_have_partitioned_false():
    df = pl.DataFrame({"id": pl.Series([1], dtype=pl.Int64), "val": pl.Series([1.0], dtype=pl.Float64)})
    with _read_ctx(df, partition_columns=[]):
        doc = DeltaReader().read("/fake/path", "t")
    assert all(not c.partitioned for c in doc.columns)


def test_partitioned_table_lists_partition_columns():
    df = pl.DataFrame({"id": pl.Series([1], dtype=pl.Int64), "region": pl.Series(["eu"], dtype=pl.String)})
    with _read_ctx(df, partition_columns=["region"]):
        doc = DeltaReader().read("/fake/path", "t")
    assert doc.partitionColumns == ["region"]


def test_partition_column_is_marked_partitioned():
    df = pl.DataFrame({"id": pl.Series([1], dtype=pl.Int64), "region": pl.Series(["eu"], dtype=pl.String)})
    with _read_ctx(df, partition_columns=["region"]):
        doc = DeltaReader().read("/fake/path", "t")
    by_name = {c.name: c for c in doc.columns}
    assert by_name["region"].partitioned is True
    assert by_name["id"].partitioned is False


def test_multi_column_partition():
    df = pl.DataFrame({
        "id":    pl.Series([1], dtype=pl.Int64),
        "year":  pl.Series([2024], dtype=pl.Int32),
        "month": pl.Series([1], dtype=pl.Int32),
    })
    with _read_ctx(df, partition_columns=["year", "month"]):
        doc = DeltaReader().read("/fake/path", "t")
    assert set(doc.partitionColumns) == {"year", "month"}
    by_name = {c.name: c for c in doc.columns}
    assert by_name["year"].partitioned is True
    assert by_name["month"].partitioned is True
    assert by_name["id"].partitioned is False
