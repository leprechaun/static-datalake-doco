"""
Tests for the polars dtype → dataType string mapping in DeltaReader.
Each test writes a single-column Delta table, reads it back, and asserts
the dataType field in the resulting Column.
"""
from datetime import date, datetime
from decimal import Decimal

import deltalake
import polars as pl
import pytest

from datalake_doco.readers.delta import DeltaReader


def _read_col(path: str) -> object:
    doc = DeltaReader().read(path, "t")
    return doc.columns[0]


# ── Scalar integer types ──────────────────────────────────────────────────────

@pytest.mark.parametrize("dtype,expected", [
    (pl.Int8,  "TINYINT"),
    (pl.Int16, "SMALLINT"),
    (pl.Int32, "INT"),
    (pl.Int64, "BIGINT"),
])
def test_signed_integer_mapping(tmp_path, dtype, expected):
    df = pl.DataFrame({"col": pl.Series([1, 2, 3], dtype=dtype)})
    path = str(tmp_path / "t")
    deltalake.write_deltalake(path, df)
    assert _read_col(path).dataType == expected


@pytest.mark.parametrize("dtype,expected", [
    (pl.UInt8,  "TINYINT"),
    (pl.UInt16, "SMALLINT"),
    (pl.UInt32, "INT"),
    (pl.UInt64, "BIGINT"),
])
def test_unsigned_integer_mapping(tmp_path, dtype, expected):
    df = pl.DataFrame({"col": pl.Series([1, 2, 3], dtype=dtype)})
    path = str(tmp_path / "t")
    deltalake.write_deltalake(path, df)
    assert _read_col(path).dataType == expected


# ── Float types ───────────────────────────────────────────────────────────────

def test_float32_maps_to_float(tmp_path):
    df = pl.DataFrame({"col": pl.Series([1.0, 2.0], dtype=pl.Float32)})
    path = str(tmp_path / "t")
    deltalake.write_deltalake(path, df)
    assert _read_col(path).dataType == "FLOAT"


def test_float64_maps_to_double(tmp_path):
    df = pl.DataFrame({"col": pl.Series([1.0, 2.0], dtype=pl.Float64)})
    path = str(tmp_path / "t")
    deltalake.write_deltalake(path, df)
    assert _read_col(path).dataType == "DOUBLE"


# ── Other scalar types ────────────────────────────────────────────────────────

def test_boolean_mapping(tmp_path):
    df = pl.DataFrame({"col": pl.Series([True, False, True], dtype=pl.Boolean)})
    path = str(tmp_path / "t")
    deltalake.write_deltalake(path, df)
    assert _read_col(path).dataType == "BOOLEAN"


def test_string_mapping(tmp_path):
    df = pl.DataFrame({"col": pl.Series(["a", "b"], dtype=pl.String)})
    path = str(tmp_path / "t")
    deltalake.write_deltalake(path, df)
    assert _read_col(path).dataType == "STRING"


def test_date_mapping(tmp_path):
    df = pl.DataFrame({"col": pl.Series([date(2024, 1, 1), date(2024, 6, 1)], dtype=pl.Date)})
    path = str(tmp_path / "t")
    deltalake.write_deltalake(path, df)
    assert _read_col(path).dataType == "DATE"


def test_datetime_maps_to_timestamp(tmp_path):
    df = pl.DataFrame({"col": pl.Series([datetime(2024, 1, 1), datetime(2024, 6, 1)], dtype=pl.Datetime("us"))})
    path = str(tmp_path / "t")
    deltalake.write_deltalake(path, df)
    assert _read_col(path).dataType == "TIMESTAMP"


def test_binary_mapping(tmp_path):
    df = pl.DataFrame({"col": pl.Series([b"hello", b"world"], dtype=pl.Binary)})
    path = str(tmp_path / "t")
    deltalake.write_deltalake(path, df)
    assert _read_col(path).dataType == "BINARY"


# ── Parametric types ──────────────────────────────────────────────────────────

def test_decimal_maps_to_decimal_with_precision_and_scale(tmp_path):
    df = pl.DataFrame({"col": pl.Series([Decimal("1.23"), Decimal("4.56")], dtype=pl.Decimal(precision=10, scale=2))})
    path = str(tmp_path / "t")
    deltalake.write_deltalake(path, df)
    col = _read_col(path)
    assert col.dataType == "DECIMAL"
    assert col.precision == 10
    assert col.scale == 2


def test_decimal_precision_and_scale_are_none_for_non_decimal(tmp_path):
    df = pl.DataFrame({"col": pl.Series([1, 2], dtype=pl.Int64)})
    path = str(tmp_path / "t")
    deltalake.write_deltalake(path, df)
    col = _read_col(path)
    assert col.precision is None
    assert col.scale is None


def test_list_maps_to_array(tmp_path):
    df = pl.DataFrame({"col": pl.Series([[1, 2], [3, 4]], dtype=pl.List(pl.Int64))})
    path = str(tmp_path / "t")
    deltalake.write_deltalake(path, df)
    assert _read_col(path).dataType == "ARRAY"


def test_struct_maps_to_struct(tmp_path):
    df = pl.DataFrame({"col": pl.Series([{"a": 1}, {"a": 2}], dtype=pl.Struct({"a": pl.Int64}))})
    path = str(tmp_path / "t")
    deltalake.write_deltalake(path, df)
    assert _read_col(path).dataType == "STRUCT"
