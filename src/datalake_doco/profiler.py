import math

import polars as pl


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


def _temporal_exprs(col: str) -> list[pl.Expr]:
    c = pl.col(col)
    return [
        c.count().alias(f"{col}__count"),
        c.null_count().alias(f"{col}__null_count"),
    ]


def _format_top(v) -> str | None:
    if v is None:
        return None
    return v.isoformat() if hasattr(v, "isoformat") else str(v)


def profile(lf: pl.LazyFrame, schema: dict[str, pl.DataType]) -> dict[str, dict]:
    """Return per-column statistics with OpenMetadata-aligned field names.

    Computes every column's count/null_count/type-specific aggregate in a single
    streaming pass over `lf`, instead of materialising the whole table first.

    Temporal columns (Date/Datetime/Duration/Time) skip n_unique and top/freq:
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
        exprs.extend(_temporal_exprs(col))
    for col in other_cols:
        exprs.extend(_other_exprs(col))

    agg = lf.select(exprs).collect(engine="streaming").row(0, named=True)

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
        }

    for col in other_cols:
        top = _format_top(agg[f"{col}__top"])
        result[col] = {
            "valuesCount": _safe_float(agg[f"{col}__count"]),
            "nullCount": _safe_float(agg[f"{col}__null_count"]),
            "uniqueCount": agg[f"{col}__n_unique"],
            "top": top,
            "freq": int(agg[f"{col}__freq"]) if top is not None else None,
        }

    return result
