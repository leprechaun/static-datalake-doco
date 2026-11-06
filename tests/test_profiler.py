import math
from datetime import UTC, date, datetime, timedelta

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
    assert set(col.keys()) == {"valuesCount", "nullCount", "min", "max", "distribution"}


def test_temporal_stats_values():
    df = pl.DataFrame({"d": pl.Series([date(2024, 1, 3), None, date(2024, 1, 1)], dtype=pl.Date)})
    col = profile(df.lazy(), df.schema)["d"]
    assert col["valuesCount"] == 2.0
    assert col["nullCount"] == 1.0
    assert col["min"] == "2024-01-01"
    assert col["max"] == "2024-01-03"


def test_datetime_min_max_are_iso_strings():
    df = pl.DataFrame({"ts": pl.Series([datetime(2024, 5, 1, 12, 30), datetime(2024, 1, 1, 8, 0)], dtype=pl.Datetime)})
    col = profile(df.lazy(), df.schema)["ts"]
    assert col["min"] == "2024-01-01T08:00:00"
    assert col["max"] == "2024-05-01T12:30:00"


def test_all_nulls_temporal_has_none_min_max():
    df = pl.DataFrame({"d": pl.Series([None, None], dtype=pl.Date)})
    col = profile(df.lazy(), df.schema)["d"]
    assert col["min"] is None
    assert col["max"] is None


def test_temporal_columns_skip_cardinality_and_numeric_keys():
    df = pl.DataFrame({"ts": pl.Series([datetime(2024, 1, 1), datetime(2024, 1, 1)], dtype=pl.Datetime)})
    col = profile(df.lazy(), df.schema)["ts"]
    for key in ("uniqueCount", "top", "freq", "mean", "stddev", "firstQuartile", "median", "thirdQuartile"):
        assert key not in col, f"unexpected key: {key}"


# ── Temporal distribution ─────────────────────────────────────────────────────

def test_datetime_distribution_rolls_up_calendar_buckets():
    df = pl.DataFrame({"ts": pl.Series([
        datetime(2024, 1, 1, 8, 15),   # Mon
        datetime(2024, 1, 1, 8, 45),   # Mon, same hour
        datetime(2024, 1, 2, 23, 0),   # Tue
        datetime(2025, 3, 9, 0, 30),   # Sun
        None,
    ], dtype=pl.Datetime)})
    dist = profile(df.lazy(), df.schema)["ts"]["distribution"]
    assert dist["year"] == {"2024": 3, "2025": 1}
    assert dist["month"] == {"2024-01": 3, "2025-03": 1}
    assert dist["day"] == {"2024-01-01": 2, "2024-01-02": 1, "2025-03-09": 1}
    assert dist["weekday"] == {"Mon": 2, "Tue": 1, "Wed": 0, "Thu": 0, "Fri": 0, "Sat": 0, "Sun": 1}
    assert len(dist["hour"]) == 24
    assert dist["hour"]["08"] == 2
    assert dist["hour"]["23"] == 1
    assert dist["hour"]["00"] == 1
    assert dist["hour"]["12"] == 0


def test_distribution_gaps():
    df = pl.DataFrame({"d": pl.Series([date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 5), date(2024, 1, 7)], dtype=pl.Date)})
    dist = profile(df.lazy(), df.schema)["d"]["distribution"]
    assert dist["daysWithData"] == 4
    assert dist["missingDays"] == 3
    assert dist["largestGap"] == {"start": "2024-01-03", "end": "2024-01-04", "days": 2}


def test_date_distribution_has_no_hours():
    df = pl.DataFrame({"d": pl.Series([date(2024, 1, 1)], dtype=pl.Date)})
    dist = profile(df.lazy(), df.schema)["d"]["distribution"]
    assert "hour" not in dist
    assert dist["largestGap"] is None
    assert dist["missingDays"] == 0


def test_distribution_is_none_without_values():
    df = pl.DataFrame({"d": pl.Series([None, None], dtype=pl.Date)})
    assert profile(df.lazy(), df.schema)["d"]["distribution"] is None


def test_distribution_handles_column_named_count():
    df = pl.DataFrame({"count": pl.Series([date(2024, 1, 1)], dtype=pl.Date)})
    assert profile(df.lazy(), df.schema)["count"]["distribution"]["day"] == {"2024-01-01": 1}


def test_duration_has_no_distribution():
    df = pl.DataFrame({"dur": pl.Series([timedelta(minutes=5)], dtype=pl.Duration)})
    assert "distribution" not in profile(df.lazy(), df.schema)["dur"]


def test_monthly_date_column_grain():
    df = pl.DataFrame({"ym": pl.Series([date(2026, 9, 1), date(2026, 10, 1), date(2026, 11, 1)], dtype=pl.Date)})
    assert profile(df.lazy(), df.schema)["ym"]["distribution"]["grain"] == "monthly"


def test_midnight_timestamps_are_daily():
    df = pl.DataFrame({"ts": pl.Series([datetime(2026, 9, 1), datetime(2026, 9, 2)], dtype=pl.Datetime)})
    dist = profile(df.lazy(), df.schema)["ts"]["distribution"]
    assert dist["grain"] == "daily"
    assert "hour" not in dist


def test_timestamps_with_a_time_are_sub_daily():
    df = pl.DataFrame({"ts": pl.Series([datetime(2026, 9, 1), datetime(2026, 9, 2, 0, 0, 1)], dtype=pl.Datetime)})
    assert profile(df.lazy(), df.schema)["ts"]["distribution"]["grain"] == "sub-daily"


def test_tz_aware_timestamps_are_bucketed_in_utc():
    # Built with expressions: on Python 3.15, polars 1.42's Series namespace methods (Series.dt.*)
    # return None, and it can't infer a dtype for a plain list of datetimes.
    df = pl.DataFrame({"ts": pl.Series([datetime(2024, 1, 2, 8, 30)], dtype=pl.Datetime)})
    df = df.with_columns(pl.col("ts").dt.replace_time_zone("Asia/Tokyo"))
    dist = profile(df.lazy(), df.schema)["ts"]["distribution"]
    assert dist["bucketing"] == "UTC"
    assert dist["day"] == {"2024-01-01": 1}
    assert dist["hour"]["23"] == 1


def test_naive_timestamps_are_bucketed_as_stored():
    df = pl.DataFrame({"ts": pl.Series([datetime(2024, 1, 2, 8, 30)], dtype=pl.Datetime)})
    dist = profile(df.lazy(), df.schema)["ts"]["distribution"]
    assert dist["bucketing"] == "naive"
    assert dist["hour"]["08"] == 1


def test_partial_period_follows_now():
    df = pl.DataFrame({"d": pl.Series([date(2026, 11, 5), date(2026, 11, 6)], dtype=pl.Date)})
    dist = profile(df.lazy(), df.schema, now=datetime(2026, 11, 6, 9, 0, tzinfo=UTC))["d"]["distribution"]
    assert dist["partialDay"] == "2026-11-06"
    assert dist["partialMonth"] == "2026-11"


def test_derived_date_column_points_at_timestamp():
    df = pl.DataFrame({
        "ts": pl.Series([datetime(2024, 1, 1, 8), datetime(2024, 1, 2, 9)], dtype=pl.Datetime),
        "date": pl.Series([date(2024, 1, 1), date(2024, 1, 2)], dtype=pl.Date),
    })
    result = profile(df.lazy(), df.schema)
    assert result["date"]["distribution"]["sameAs"] == {"column": "ts", "relation": "derived"}
    assert "sameAs" not in result["ts"]["distribution"]


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
