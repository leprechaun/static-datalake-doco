from datetime import UTC, date, datetime

from datalake_doco.timeseries import (
    build_distribution,
    detect_grain,
    mark_duplicates,
    missing_day_ranges,
    missing_month_ranges,
    rows_per_day,
)

NOW = datetime(2026, 11, 6, 13, 0, tzinfo=UTC)


def _daily(counts: dict[str, int]) -> list[dict]:
    return [{"bucket": date.fromisoformat(d), "count": n} for d, n in counts.items()]


# ── Grain ─────────────────────────────────────────────────────────────────────

def test_grain_sub_daily_when_any_value_is_off_midnight():
    assert detect_grain(off_midnight=True, off_first=False, distinct_days=5) == "sub-daily"


def test_grain_monthly_when_every_value_is_the_first():
    assert detect_grain(off_midnight=False, off_first=False, distinct_days=3) == "monthly"


def test_grain_daily_when_midnight_but_not_always_the_first():
    assert detect_grain(off_midnight=False, off_first=True, distinct_days=3) == "daily"


def test_grain_single_first_of_month_is_daily():
    assert detect_grain(off_midnight=False, off_first=False, distinct_days=1) == "daily"


# ── Gap ranges ────────────────────────────────────────────────────────────────

def test_missing_day_ranges_largest_first():
    days = [date(2024, 1, d) for d in (1, 3, 4, 9, 10)]
    assert missing_day_ranges(days) == [
        {"start": "2024-01-05", "end": "2024-01-08", "count": 4},
        {"start": "2024-01-02", "end": "2024-01-02", "count": 1},
    ]


def test_missing_day_ranges_none_when_contiguous():
    assert missing_day_ranges([date(2024, 1, 1), date(2024, 1, 2)]) == []


def test_missing_month_ranges_collapse_consecutive_months_across_years():
    months = [date(2024, 10, 1), date(2025, 2, 1), date(2025, 4, 1)]
    assert missing_month_ranges(months) == [
        {"start": "2024-11", "end": "2025-01", "count": 3},
        {"start": "2025-03", "end": "2025-03", "count": 1},
    ]


# ── Rows per day ──────────────────────────────────────────────────────────────

def test_rows_per_day_quantiles():
    r = rows_per_day(list(range(1, 102)))  # 1..101
    assert r == {"min": 1, "p5": 6.0, "median": 51.0, "p95": 96.0, "max": 101}


def test_rows_per_day_empty():
    assert rows_per_day([]) is None


# ── Distribution ──────────────────────────────────────────────────────────────

def test_partial_day_excluded_from_rows_per_day():
    dist = build_distribution(_daily({"2026-11-04": 100, "2026-11-05": 100, "2026-11-06": 3}), "daily", "date", NOW)
    assert dist["partialDay"] == "2026-11-06"
    assert dist["partialMonth"] == "2026-11"
    assert dist["rowsPerDay"]["min"] == 100
    assert dist["day"]["2026-11-06"] == 3


def test_monthly_distribution_reports_missing_months_not_days():
    dist = build_distribution(_daily({"2026-07-01": 5, "2026-09-01": 7, "2026-10-01": 2}), "monthly", "date", NOW)
    assert dist["gaps"] == [{"start": "2026-08", "end": "2026-08", "count": 1}]
    assert "rowsPerDay" not in dist


def test_daily_timestamps_have_no_hour_table():
    buckets = [{"bucket": datetime(2026, 1, d), "count": 1} for d in (1, 2)]
    assert "hour" not in build_distribution(buckets, "daily", "naive", NOW)


def test_sub_daily_timestamps_have_hour_table():
    buckets = [{"bucket": datetime(2026, 1, 1, 7), "count": 4}]
    dist = build_distribution(buckets, "sub-daily", "naive", NOW)
    assert dist["hour"]["07"] == 4


def test_distribution_records_grain_and_bucketing():
    dist = build_distribution(_daily({"2026-01-01": 1}), "daily", "date", NOW)
    assert dist["grain"] == "daily"
    assert dist["bucketing"] == "date"


# ── Duplicates ────────────────────────────────────────────────────────────────

def test_date_matching_timestamp_is_derived():
    dists = {"date": {"day": {"2024-01-01": 2}}, "ts": {"day": {"2024-01-01": 2}}}
    mark_duplicates(dists, {"date": "date", "ts": "datetime"})
    assert dists["date"]["sameAs"] == {"column": "ts", "relation": "derived"}
    assert "sameAs" not in dists["ts"]


def test_matching_timestamps_are_identical_and_point_at_the_first():
    dists = {"a": {"day": {"2024-01-01": 2}}, "b": {"day": {"2024-01-01": 2}}, "c": {"day": {"2024-01-01": 2}}}
    mark_duplicates(dists, {"a": "datetime", "b": "datetime", "c": "datetime"})
    assert dists["b"]["sameAs"] == {"column": "a", "relation": "identical"}
    assert dists["c"]["sameAs"] == {"column": "a", "relation": "identical"}


def test_different_counts_are_not_duplicates():
    dists = {"a": {"day": {"2024-01-01": 2}}, "b": {"day": {"2024-01-01": 3}}}
    mark_duplicates(dists, {"a": "datetime", "b": "datetime"})
    assert "sameAs" not in dists["b"]
