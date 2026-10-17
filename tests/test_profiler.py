import math
from datetime import date, datetime

import polars as pl
import pytest

from datalake_doco.profiler import profile

# ── Numeric columns ───────────────────────────────────────────────────────────

def test_numeric_stats_fields_present():
    df = pl.DataFrame({"x": pl.Series([1.0, 2.0, 3.0, 4.0, 5.0], dtype=pl.Float64)})
    col = profile(df.lazy(), df.schema)["x"]
    for key in ("valuesCount", "nullCount", "mean", "stddev", "min", "firstQuartile", "median", "thirdQuartile", "max"):
        assert key in col, f"missing key: {key}"


def test_numeric_stats_values():
    df = pl.DataFrame({"x": pl.Series([1.0, 2.0, 3.0, 4.0, 5.0], dtype=pl.Float64)})
    col = profile(df.lazy(), df.schema)["x"]
    assert col["valuesCount"] == 5.0
    assert col["nullCount"] == 0.0
    assert col["mean"] == pytest.approx(3.0)
    assert col["min"] == 1.0
    assert col["max"] == 5.0
    assert col["median"] == pytest.approx(3.0)


def test_numeric_columns_have_no_categorical_keys():
    df = pl.DataFrame({"x": pl.Series([1.0, 2.0, 3.0], dtype=pl.Float64)})
    col = profile(df.lazy(), df.schema)["x"]
    for key in ("uniqueCount", "top", "freq"):
        assert key not in col


# ── String / categorical columns ──────────────────────────────────────────────

def test_categorical_stats_fields_present():
    df = pl.DataFrame({"cat": pl.Series(["a", "b", "a"], dtype=pl.String)})
    col = profile(df.lazy(), df.schema)["cat"]
    for key in ("valuesCount", "nullCount", "uniqueCount", "top", "freq"):
        assert key in col, f"missing key: {key}"


def test_categorical_stats_values():
    df = pl.DataFrame({"cat": pl.Series(["a", "b", "a", "a", "b"], dtype=pl.String)})
    col = profile(df.lazy(), df.schema)["cat"]
    assert col["valuesCount"] == 5.0
    assert col["nullCount"] == 0.0
    assert col["uniqueCount"] == 2
    assert col["top"] == "a"
    assert col["freq"] == 3


def test_categorical_columns_have_no_numeric_keys():
    df = pl.DataFrame({"cat": pl.Series(["x", "y"], dtype=pl.String)})
    col = profile(df.lazy(), df.schema)["cat"]
    for key in ("mean", "stddev", "min", "firstQuartile", "median", "thirdQuartile", "max"):
        assert key not in col


# ── Temporal columns ──────────────────────────────────────────────────────────

def test_temporal_stats_fields_present():
    df = pl.DataFrame({"ts": pl.Series([datetime(2024, 1, 1), datetime(2024, 1, 2)], dtype=pl.Datetime)})
    col = profile(df.lazy(), df.schema)["ts"]
    assert set(col.keys()) == {"valuesCount", "nullCount"}


def test_temporal_stats_values():
    df = pl.DataFrame({"d": pl.Series([date(2024, 1, 1), None, date(2024, 1, 3)], dtype=pl.Date)})
    col = profile(df.lazy(), df.schema)["d"]
    assert col["valuesCount"] == 2.0
    assert col["nullCount"] == 1.0


def test_temporal_columns_skip_cardinality_and_numeric_keys():
    df = pl.DataFrame({"ts": pl.Series([datetime(2024, 1, 1), datetime(2024, 1, 1)], dtype=pl.Datetime)})
    col = profile(df.lazy(), df.schema)["ts"]
    for key in ("uniqueCount", "top", "freq", "mean", "stddev", "min", "firstQuartile", "median", "thirdQuartile", "max"):
        assert key not in col, f"unexpected key: {key}"


# ── Null handling ─────────────────────────────────────────────────────────────

def test_null_count_numeric():
    df = pl.DataFrame({"x": pl.Series([1.0, None, 3.0, None], dtype=pl.Float64)})
    col = profile(df.lazy(), df.schema)["x"]
    assert col["nullCount"] == 2.0
    assert col["valuesCount"] == 2.0


def test_null_count_categorical():
    df = pl.DataFrame({"cat": pl.Series(["a", None, "a", None], dtype=pl.String)})
    col = profile(df.lazy(), df.schema)["cat"]
    assert col["nullCount"] == 2.0
    assert col["valuesCount"] == 2.0


def test_top_value_excludes_nulls():
    # "a" appears twice, None appears twice — null should not be the top value
    df = pl.DataFrame({"cat": pl.Series(["a", None, "a", None], dtype=pl.String)})
    col = profile(df.lazy(), df.schema)["cat"]
    assert col["top"] == "a"


def test_all_nulls_categorical_has_none_top():
    df = pl.DataFrame({"cat": pl.Series([None, None], dtype=pl.String)})
    col = profile(df.lazy(), df.schema)["cat"]
    assert col["top"] is None
    assert col["freq"] is None


# ── NaN / Inf safety ──────────────────────────────────────────────────────────

def test_no_nan_or_inf_in_numeric_stats():
    df = pl.DataFrame({"x": pl.Series([float("nan"), float("inf"), 1.0], dtype=pl.Float64)})
    col = profile(df.lazy(), df.schema)["x"]
    for key in ("mean", "stddev", "min", "firstQuartile", "median", "thirdQuartile", "max"):
        v = col[key]
        if v is not None:
            assert not math.isnan(v), f"{key} is NaN"
            assert not math.isinf(v), f"{key} is Inf"


# ── Multi-column coverage ─────────────────────────────────────────────────────

def test_all_columns_returned():
    df = pl.DataFrame({
        "num": pl.Series([1.0, 2.0, 3.0], dtype=pl.Float64),
        "cat": pl.Series(["x", "y", "x"], dtype=pl.String),
    })
    result = profile(df.lazy(), df.schema)
    assert set(result.keys()) == {"num", "cat"}


def test_column_profiles_are_independent():
    df = pl.DataFrame({
        "num": pl.Series([1.0, 2.0, 3.0], dtype=pl.Float64),
        "cat": pl.Series(["x", "y", "x"], dtype=pl.String),
    })
    result = profile(df.lazy(), df.schema)
    assert "mean" in result["num"]
    assert "uniqueCount" in result["cat"]
    assert "mean" not in result["cat"]
    assert "uniqueCount" not in result["num"]
