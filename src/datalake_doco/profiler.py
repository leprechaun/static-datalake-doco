import math
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import polars as pl

from datalake_doco.config import BUCKET_TIMEZONE
from datalake_doco.timeseries import build_distribution, detect_grain, mark_duplicates


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return None if math.isnan(f) or math.isinf(f) else round(f, 6)
    except (TypeError, ValueError):
        return None


def _numeric_exprs(col: str) -> list[pl.Expr]:
    c = pl.col(col)
    return [
        c.count().alias(f"{col}__count"),
        c.null_count().alias(f"{col}__null_count"),
        c.mean().alias(f"{col}__mean"),
        c.std().alias(f"{col}__std"),
        c.min().alias(f"{col}__min"),
        c.quantile(0.25).alias(f"{col}__q1"),
        c.median().alias(f"{col}__median"),
        c.quantile(0.75).alias(f"{col}__q3"),
        c.max().alias(f"{col}__max"),
    ]


def _other_exprs(col: str) -> list[pl.Expr]:
    c = pl.col(col)
    top = c.drop_nulls().mode().first()
    return [
        c.count().alias(f"{col}__count"),
        c.null_count().alias(f"{col}__null_count"),
        c.n_unique().alias(f"{col}__n_unique"),
        top.alias(f"{col}__top"),
        (c == top).sum().alias(f"{col}__freq"),
    ]


def _temporal_exprs(col: str, dtype: pl.DataType) -> list[pl.Expr]:
    c = pl.col(col)
    exprs = [
        c.count().alias(f"{col}__count"),
        c.null_count().alias(f"{col}__null_count"),
        c.min().alias(f"{col}__min"),
        c.max().alias(f"{col}__max"),
    ]
    if _has_distribution(dtype):
        values = c.drop_nulls()
        if isinstance(dtype, pl.Datetime) and dtype.time_zone:
            values = values.dt.convert_time_zone(BUCKET_TIMEZONE)
        bucket = values if dtype == pl.Date else values.dt.truncate("1h")
        exprs += [
            bucket.alias("bucket").value_counts(name="count").implode().alias(f"{col}__buckets"),
            (values.dt.day() != 1).any().alias(f"{col}__off_first"),
        ]
        if dtype != pl.Date:
            exprs.append((values != values.dt.truncate("1d")).any().alias(f"{col}__off_midnight"))
    return exprs


def _has_distribution(dtype: pl.DataType) -> bool:
    return dtype == pl.Date or isinstance(dtype, pl.Datetime)


def _bucketing(dtype: pl.DataType) -> str:
    """How values were bucketed: the time zone tz-aware timestamps were converted to, or
    'naive'/'date' for values bucketed as stored."""
    if dtype == pl.Date:
        return "date"
    return BUCKET_TIMEZONE if dtype.time_zone else "naive"


def _distribution(col: str, dtype: pl.DataType, agg: dict, now: datetime) -> dict | None:
    buckets = agg[f"{col}__buckets"]
    distinct_days = len({b["bucket"] if dtype == pl.Date else b["bucket"].date() for b in buckets})
    grain = detect_grain(bool(agg.get(f"{col}__off_midnight")), bool(agg[f"{col}__off_first"]), distinct_days)
    return build_distribution(buckets, grain, _bucketing(dtype), now.astimezone(ZoneInfo(BUCKET_TIMEZONE)))


def _format_value(v) -> str | None:
    if v is None:
        return None
    return v.isoformat() if hasattr(v, "isoformat") else str(v)


def profile(lf: pl.LazyFrame, schema: dict[str, pl.DataType], now: datetime | None = None) -> dict[str, dict]:
    """Return per-column statistics with OpenMetadata-aligned field names.

    Computes every column's count/null_count/type-specific aggregate in a single
    streaming pass over `lf`, instead of materialising the whole table first.

    Temporal columns (Date/Datetime/Duration/Time) get min/max as ISO strings and,
    for Date/Datetime, a calendar distribution (see `timeseries.build_distribution`)
    built from per-day or per-hour counts gathered in the same pass, with `now` (the
    profiling time) marking the partial day and month. They skip n_unique and top/freq:
    they're typically near-unique per row (e.g. a per-reading timestamp), so a
    full value_counts/group-by pass over them is expensive and the result
    (freq≈1) isn't meaningful.

    top/freq for other_cols is computed via mode() inside the same pass rather
    than a separate value_counts() query — on a remote table (e.g. S3-backed
    Delta), a separate query per column means a separate full table scan per
    column, which dominates wall time even when the data itself is small.
    """
    numeric_cols = [col for col, dtype in schema.items() if dtype.is_numeric()]
    temporal_cols = [col for col, dtype in schema.items() if dtype.is_temporal()]
    other_cols = [col for col in schema if col not in numeric_cols and col not in temporal_cols]

    exprs: list[pl.Expr] = []
    for col in numeric_cols:
        exprs.extend(_numeric_exprs(col))
    for col in temporal_cols:
        exprs.extend(_temporal_exprs(col, schema[col]))
    for col in other_cols:
        exprs.extend(_other_exprs(col))

    agg = lf.select(exprs).collect(engine="streaming").row(0, named=True)
    now = now or datetime.now(UTC)

    result: dict[str, dict] = {}

    for col in numeric_cols:
        result[col] = {
            "valuesCount": _safe_float(agg[f"{col}__count"]),
            "nullCount": _safe_float(agg[f"{col}__null_count"]),
            "mean": _safe_float(agg[f"{col}__mean"]),
            "stddev": _safe_float(agg[f"{col}__std"]),
            "min": _safe_float(agg[f"{col}__min"]),
            "firstQuartile": _safe_float(agg[f"{col}__q1"]),
            "median": _safe_float(agg[f"{col}__median"]),
            "thirdQuartile": _safe_float(agg[f"{col}__q3"]),
            "max": _safe_float(agg[f"{col}__max"]),
        }

    for col in temporal_cols:
        result[col] = {
            "valuesCount": _safe_float(agg[f"{col}__count"]),
            "nullCount": _safe_float(agg[f"{col}__null_count"]),
            "min": _format_value(agg[f"{col}__min"]),
            "max": _format_value(agg[f"{col}__max"]),
        }
        if _has_distribution(schema[col]):
            result[col]["distribution"] = _distribution(col, schema[col], agg, now)

    for col in other_cols:
        top = _format_value(agg[f"{col}__top"])
        result[col] = {
            "valuesCount": _safe_float(agg[f"{col}__count"]),
            "nullCount": _safe_float(agg[f"{col}__null_count"]),
            "uniqueCount": agg[f"{col}__n_unique"],
            "top": top,
            "freq": int(agg[f"{col}__freq"]) if top is not None else None,
        }

    distributions = {col: result[col]["distribution"] for col in temporal_cols if result[col].get("distribution")}
    mark_duplicates(distributions, {col: "date" if schema[col] == pl.Date else "datetime" for col in distributions})

    return result
