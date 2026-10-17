"""
Tests for the polars dtype → dataType string mapping.
_polars_type is a pure function — no Delta tables or mocking needed.
"""
import polars as pl
import pytest

from datalake_doco.readers.delta import _polars_type


@pytest.mark.parametrize("dtype,expected", [
    (pl.Int8(),   "TINYINT"),
    (pl.Int16(),  "SMALLINT"),
    (pl.Int32(),  "INT"),
    (pl.Int64(),  "BIGINT"),
    (pl.UInt8(),  "TINYINT"),
    (pl.UInt16(), "SMALLINT"),
    (pl.UInt32(), "INT"),
    (pl.UInt64(), "BIGINT"),
    (pl.Float32(), "FLOAT"),
    (pl.Float64(), "DOUBLE"),
    (pl.Boolean(), "BOOLEAN"),
    (pl.String(),  "STRING"),
    (pl.Date(),    "DATE"),
    (pl.Binary(),  "BINARY"),
    (pl.Datetime("us"), "TIMESTAMP"),
    (pl.List(pl.Int64()),         "ARRAY"),
    (pl.Struct({"a": pl.Int64()}), "STRUCT"),
])
def test_type_string(dtype, expected):
    data_type, _, _ = _polars_type(dtype)
    assert data_type == expected


def test_decimal_type_string():
    data_type, _, _ = _polars_type(pl.Decimal(precision=10, scale=2))
    assert data_type == "DECIMAL"


def test_decimal_carries_precision_and_scale():
    _, precision, scale = _polars_type(pl.Decimal(precision=10, scale=2))
    assert precision == 10
    assert scale == 2


def test_non_decimal_has_no_precision_or_scale():
    for dtype in (pl.Int64(), pl.Float64(), pl.String(), pl.Boolean()):
        _, precision, scale = _polars_type(dtype)
        assert precision is None
        assert scale is None
