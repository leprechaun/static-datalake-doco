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


def profile(df: pl.DataFrame) -> dict[str, dict]:
    """Return per-column statistics with OpenMetadata-aligned field names."""
    desc = df.describe()

    col_stats: dict[str, dict] = {}
    for row in desc.iter_rows(named=True):
        stat = row["statistic"]
        for col, val in row.items():
            if col == "statistic":
                continue
            col_stats.setdefault(col, {})[stat] = val

    result: dict[str, dict] = {}
    for col in df.columns:
        s = col_stats.get(col, {})
        dtype = df[col].dtype

        if dtype.is_numeric():
            result[col] = {
                "valuesCount": _safe_float(s.get("count")),
                "nullCount": _safe_float(s.get("null_count")),
                "mean": _safe_float(s.get("mean")),
                "stddev": _safe_float(s.get("std")),
                "min": _safe_float(s.get("min")),
                "firstQuartile": _safe_float(s.get("25%")),
                "median": _safe_float(s.get("50%")),
                "thirdQuartile": _safe_float(s.get("75%")),
                "max": _safe_float(s.get("max")),
            }
        else:
            vc = df[col].drop_nulls().value_counts(sort=True)
            top: str | None = None
            freq: int | None = None
            if vc.height > 0:
                top_row = vc.row(0, named=True)
                v = top_row[col]
                top = v.isoformat() if hasattr(v, "isoformat") else str(v)
                freq = int(top_row["count"])

            result[col] = {
                "valuesCount": _safe_float(s.get("count")),
                "nullCount": _safe_float(s.get("null_count")),
                "uniqueCount": df[col].n_unique(),
                "top": top,
                "freq": freq,
            }

    return result
