import math

import polars as pl

from datalake_doco.models import ColumnStats


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return None if math.isnan(f) or math.isinf(f) else round(f, 6)
    except (TypeError, ValueError):
        return None


def profile(df: pl.DataFrame) -> dict[str, ColumnStats]:
    desc = df.describe()

    # Pivot describe output into {col: {stat: value}}
    col_stats: dict[str, dict] = {}
    for row in desc.iter_rows(named=True):
        stat = row["statistic"]
        for col, val in row.items():
            if col == "statistic":
                continue
            col_stats.setdefault(col, {})[stat] = val

    result: dict[str, ColumnStats] = {}
    for col in df.columns:
        s = col_stats.get(col, {})
        dtype = df[col].dtype

        if dtype.is_numeric():
            result[col] = ColumnStats(
                count=_safe_float(s.get("count")),
                mean=_safe_float(s.get("mean")),
                std=_safe_float(s.get("std")),
                min=_safe_float(s.get("min")),
                p25=_safe_float(s.get("25%")),
                p50=_safe_float(s.get("50%")),
                p75=_safe_float(s.get("75%")),
                max=_safe_float(s.get("max")),
            )
        else:
            vc = df[col].drop_nulls().value_counts(sort=True)
            top: str | None = None
            freq: int | None = None
            if vc.height > 0:
                top_row = vc.row(0, named=True)
                v = top_row[col]
                top = v.isoformat() if hasattr(v, "isoformat") else str(v)
                freq = int(top_row["count"])

            result[col] = ColumnStats(
                count=_safe_float(s.get("count")),
                unique=df[col].n_unique(),
                top=top,
                freq=freq,
            )

    return result
