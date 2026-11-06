"""Calendar facts about a temporal column, derived from its per-hour or per-day row counts.

Everything here works on the small bucket counts the profiler gathers in its single pass, so
none of it touches the table again.
"""

from collections import Counter
from datetime import date, datetime, timedelta
from itertools import pairwise

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def detect_grain(off_midnight: bool, off_first: bool, distinct_days: int) -> str:
    """'monthly' when every value is midnight on the 1st, 'daily' when every value is midnight,
    otherwise 'sub-daily'. A single distinct day can't show a monthly pattern, so it's daily."""
    if off_midnight:
        return "sub-daily"
    if not off_first and distinct_days > 1:
        return "monthly"
    return "daily"


def _next_month(d: date) -> date:
    return date(d.year + d.month // 12, d.month % 12 + 1, 1)


def _month_key(d: date) -> str:
    return f"{d:%Y-%m}"


def missing_day_ranges(days: list[date]) -> list[dict]:
    """Runs of consecutive missing days between the first and last day, largest first."""
    gaps = [
        {"start": (prev + timedelta(days=1)).isoformat(), "end": (nxt - timedelta(days=1)).isoformat(), "count": (nxt - prev).days - 1}
        for prev, nxt in pairwise(sorted(days)) if (nxt - prev).days > 1
    ]
    return sorted(gaps, key=lambda g: (-g["count"], g["start"]))


def missing_month_ranges(months: list[date]) -> list[dict]:
    """Runs of consecutive missing months between the first and last, largest first.
    Months are given as first-of-month dates."""
    present = set(months)
    runs: list[list[date]] = []
    m = min(months)
    while m < max(months):
        if m not in present:
            if runs and _next_month(runs[-1][-1]) == m:
                runs[-1].append(m)
            else:
                runs.append([m])
        m = _next_month(m)
    gaps = [{"start": _month_key(r[0]), "end": _month_key(r[-1]), "count": len(r)} for r in runs]
    return sorted(gaps, key=lambda g: (-g["count"], g["start"]))


def _quantile(ordered: list[int], q: float) -> float:
    pos = (len(ordered) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def rows_per_day(counts: list[int]) -> dict | None:
    if not counts:
        return None
    ordered = sorted(counts)
    return {
        "min": ordered[0],
        "p5": _quantile(ordered, 0.05),
        "median": _quantile(ordered, 0.5),
        "p95": _quantile(ordered, 0.95),
        "max": ordered[-1],
    }


def build_distribution(buckets: list[dict], grain: str, bucketing: str, now: datetime) -> dict | None:
    """Roll hourly (Datetime) or daily (Date) bucket counts up into calendar distributions.

    `now` is the profiling time in the bucketing time zone. Its day and month are still in
    progress, so they're recorded as partial, and the partial day is left out of the
    rows-per-day spread. Weekday and hour are cyclic, so every slot is listed even when empty;
    year, month and day only list buckets that have rows.
    """
    if not buckets:
        return None
    hourly = isinstance(buckets[0]["bucket"], datetime)
    days: Counter[date] = Counter()
    hours: Counter[int] = Counter()
    for b in buckets:
        value, n = b["bucket"], b["count"]
        days[value.date() if hourly else value] += n
        if hourly:
            hours[value.hour] += n

    years: Counter[str] = Counter()
    months: Counter[str] = Counter()
    weekdays: Counter[str] = Counter()
    for d, n in days.items():
        years[f"{d:%Y}"] += n
        months[_month_key(d)] += n
        weekdays[WEEKDAYS[d.weekday()]] += n

    sorted_days = sorted(days)
    day_gaps = missing_day_ranges(sorted_days)
    partial_day = now.date()

    result = {
        "grain": grain,
        "bucketing": bucketing,
        "partialDay": partial_day.isoformat(),
        "partialMonth": _month_key(partial_day),
        "daysWithData": len(sorted_days),
        "missingDays": (sorted_days[-1] - sorted_days[0]).days + 1 - len(sorted_days),
        "largestGap": {"start": day_gaps[0]["start"], "end": day_gaps[0]["end"], "days": day_gaps[0]["count"]} if day_gaps else None,
        "year": dict(sorted(years.items())),
        "month": dict(sorted(months.items())),
        "day": {d.isoformat(): days[d] for d in sorted_days},
        "weekday": {w: weekdays[w] for w in WEEKDAYS},
    }
    if grain == "monthly":
        result["gaps"] = missing_month_ranges(sorted({d.replace(day=1) for d in sorted_days}))
    else:
        result["gaps"] = day_gaps
        result["rowsPerDay"] = rows_per_day([n for d, n in days.items() if d != partial_day])
    if hourly and grain == "sub-daily":
        result["hour"] = {f"{h:02d}": hours[h] for h in range(24)}
    return result


def mark_duplicates(distributions: dict[str, dict], types: dict[str, str]) -> None:
    """Point each distribution whose per-day counts repeat an earlier column's at that column.

    `distributions` is in column order and `types` maps each column to 'date' or 'datetime'.
    A date that matches a timestamp is 'derived' from it; columns of the same type are
    'identical'. Timestamps are preferred as the column others point at.
    """
    ordered = sorted(distributions, key=lambda c: types[c] != "datetime")
    for i, col in enumerate(ordered):
        for earlier in ordered[:i]:
            if "sameAs" not in distributions[earlier] and distributions[earlier]["day"] == distributions[col]["day"]:
                relation = "derived" if types[col] == "date" and types[earlier] == "datetime" else "identical"
                distributions[col]["sameAs"] = {"column": earlier, "relation": relation}
                break
