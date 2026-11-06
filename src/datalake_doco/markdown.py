"""Render the catalogue as Markdown for LLMs: an llms.txt index plus one file per table."""

import posixpath

from datalake_doco.config import MAX_GAP_RANGES
from datalake_doco.models import Catalog, CatalogEntry, Column, TableDoc

RECENT_HISTORY_COUNT = 5
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def table_md_path(fqn: str) -> str:
    return f"tables/{fqn.replace('.', '/')}.md"


def table_json_path(fqn: str) -> str:
    return f"tables/{fqn.replace('.', '/')}.json"


def group_of(fqn: str) -> str:
    """Everything but the last segment, e.g. 'gadgetbridge.gold' for 'gadgetbridge.gold.sleep'."""
    return fqn.rsplit(".", 1)[0] if "." in fqn else ""


def _link(target: str, from_path: str, base_url: str | None) -> str:
    """Absolute URL when base_url is set, otherwise a path relative to the linking file."""
    if base_url:
        return base_url.rstrip("/") + "/" + target
    return posixpath.relpath(target, posixpath.dirname(from_path) or ".")


def _inline(text: str) -> str:
    return " ".join(text.split())


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        value = f"{value:,.4f}".rstrip("0").rstrip(".")
    return _inline(str(value)).replace("|", "\\|")


def _table(headers: list[str], rows: list[list]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(_cell(v) for v in row) + " |" for row in rows]
    return lines


def _counts(values) -> list[str | None]:
    return [None if n is None else f"{n:,}" for n in values]


def _plural(n: int, unit: str) -> str:
    return f"{n:,} {unit}" if n == 1 else f"{n:,} {unit}s"


def _number(v: float) -> str:
    return f"{v:,.0f}" if v >= 100 else f"{v:,.1f}".rstrip("0").rstrip(".")


def _duration(seconds: float) -> str:
    for unit, size in (("days", 86400), ("h", 3600), ("min", 60)):
        if seconds >= 2 * size:
            value = seconds / size
            return f"{value:,.0f} {unit}" if value >= 10 else f"{value:.1f} {unit}"
    return f"{seconds:.0f} s" if seconds >= 10 else f"{seconds:.1f}".rstrip("0").rstrip(".") + " s"


def _ratio(r: float) -> str:
    return f"{r:,.0f}×" if r >= 10 else f"{r:.1f}×"


BUCKETING = {
    "naive": "Naive timestamps, bucketed as stored.",
    "date": "Dates, bucketed as stored.",
}


def _gap_lines(gaps: list[dict], unit: str) -> list[str]:
    if not gaps:
        return [f"- Missing {unit}s: none."]
    total = sum(g["count"] for g in gaps)
    lines = [f"- Missing {unit}s: {total:,}, in {_plural(len(gaps), 'gap')} (largest first):"]
    for g in gaps[:MAX_GAP_RANGES]:
        span = g["start"] if g["start"] == g["end"] else f"{g['start']} to {g['end']}"
        lines.append(f"  - {span} ({_plural(g['count'], unit)})")
    rest = gaps[MAX_GAP_RANGES:]
    if rest:
        lines.append(f"  - … {_plural(len(rest), 'more gap')} ({_plural(sum(g['count'] for g in rest), unit)})")
    return lines


def _distribution_lines(column: str, dist: dict, profiled_at: str) -> list[str]:
    same = dist.get("sameAs")
    if same:
        if same["relation"] == "derived":
            return ["", f"`{column}`: same per-day counts as `{same['column']}` (derived)."]
        return ["", f"`{column}`: identical per-day counts to `{same['column']}`."]

    grain = dist.get("grain", "daily")
    bucketing = dist.get("bucketing")
    lines = ["", f"### {column} ({grain})", ""]
    intro = BUCKETING.get(bucketing, f"Bucketed in {bucketing}.") if bucketing else ""
    days = list(dist["day"])
    if grain == "monthly":
        months = list(dist["month"])
        intro += f" Data in {_plural(len(months), 'month')} from {months[0]} to {months[-1]}."
    else:
        intro += f" Data on {_plural(len(days), 'day')} from {days[0]} to {days[-1]}."
    lines += [intro.strip(), ""]

    partial_day = dist.get("partialDay")
    if grain != "monthly" and dist.get("rowsPerDay"):
        r = dist["rowsPerDay"]
        note = f", excluding the partial day {partial_day}" if partial_day in dist["day"] else ""
        lines.append(
            f"- Rows per day (days with data{note}): min {_number(r['min'])}, p5 {_number(r['p5'])}, "
            f"median {_number(r['median'])}, p95 {_number(r['p95'])}, max {_number(r['max'])}"
        )
    lines += _gap_lines(dist.get("gaps", []), "month" if grain == "monthly" else "day")
    lines.append("")

    partial_month = dist.get("partialMonth")
    by_year: dict[str, list[str | None]] = {}
    for year_month, n in dist["month"].items():
        year, month = year_month.split("-")
        by_year.setdefault(year, [None] * 12)[int(month) - 1] = f"{n:,}\\*" if year_month == partial_month else f"{n:,}"
    lines += _table(
        ["Year", *MONTHS, "Total"],
        [[year, *months, f"{dist['year'][year]:,}"] for year, months in by_year.items()],
    )
    if partial_month in dist["month"]:
        lines += ["", f"\\* Partial period: still in progress when profiled at {profiled_at}."]

    if grain != "monthly":
        lines += ["", "Rows by weekday:", ""]
        lines += _table(list(dist["weekday"]), [_counts(dist["weekday"].values())])
    if "hour" in dist:
        lines += ["", "Rows by hour of day:", ""]
        lines += _table(list(dist["hour"]), [_counts(dist["hour"].values())])
    return lines


def _freshness_lines(freshness: dict | None) -> list[str]:
    if not freshness:
        return ["- Last data write: none in the Delta history"]
    lines = [f"- Last data write: {freshness['lastWrite']} ({_duration(freshness['secondsSinceLastWrite'])} before profiling)"]
    interval = freshness.get("typicalIntervalSeconds")
    if interval is None:
        lines.append(f"- Typical write interval: unknown ({_plural(freshness['dataCommits'], 'data write')} in the history)")
    else:
        burst = freshness.get("burstGapSeconds")
        detail = f"median of the last {_plural(freshness['intervalGaps'], 'gap')} between data writes"
        if burst:
            detail += f"; writes under {_duration(burst)} apart count as one burst"
        line = f"- Typical write interval: {_duration(interval)} ({detail})"
        if freshness.get("ratio") is not None:
            line += f"; the time since the last write is {_ratio(freshness['ratio'])} that"
        lines.append(line)
    return lines


def _freshness_hint(freshness: dict | None) -> str:
    if not freshness:
        return ""
    hint = f"last write {_duration(freshness['secondsSinceLastWrite'])} ago"
    interval = freshness.get("typicalIntervalSeconds")
    if interval is None:
        return f"{hint}, {_plural(freshness['dataCommits'], 'write')} in total"
    if freshness.get("ratio") is not None:
        return f"{hint}, {_ratio(freshness['ratio'])} its typical {_duration(interval)} interval"
    return f"{hint}, typically every {_duration(interval)}"


def render_llms_txt(catalog: Catalog, base_url: str | None = None) -> str:
    lines = [
        "# Datalake catalogue",
        "",
        (
            f"> {len(catalog.tables)} Delta Lake tables from {', '.join(catalog.sources)}. "
            f"Generated {catalog.generatedAt}; write ages are relative to that. "
            "Each link leads to a Markdown page with the table's description, schema, statistics, "
            "sample rows and related tables."
        ),
    ]

    groups: dict[str, list[CatalogEntry]] = {}
    for entry in catalog.tables:
        groups.setdefault(group_of(entry.fullyQualifiedName), []).append(entry)

    for group in sorted(groups):
        lines += ["", f"## {group or '(root)'}", ""]
        for entry in sorted(groups[group], key=lambda e: e.fullyQualifiedName):
            link = _link(table_md_path(entry.fullyQualifiedName), "llms.txt", base_url)
            summary = f"{entry.rowCount:,} rows, {entry.columnCount} columns"
            hint = _freshness_hint(entry.freshness)
            if hint:
                summary += f"; {hint}"
            if entry.description:
                summary = f"{_inline(entry.description)} ({summary})"
            lines.append(f"- [{entry.fullyQualifiedName}]({link}): {summary}")

    return "\n".join(lines) + "\n"


def _column_description(column: Column) -> str:
    """The column's description followed by its tags, e.g. "Heart rate (unit: bpm)"."""
    tags = "; ".join(f"{k}: {v}" for k, v in column.tags.items())
    if column.description and tags:
        return f"{column.description} ({tags})"
    return column.description or tags


def render_table_md(doc: TableDoc, related: list[CatalogEntry], base_url: str | None = None) -> str:
    fqn = doc.fullyQualifiedName
    here = table_md_path(fqn)
    lines = [f"# {fqn}", ""]

    if doc.description:
        lines += [f"> {line}" for line in doc.description.splitlines()] + [""]

    lines += [
        f"- Rows: {doc.tableProfile.rowCount:,}",
        f"- Columns: {len(doc.columns)}",
    ]
    if doc.partitionColumns:
        lines.append(f"- Partitioned by: {', '.join(doc.partitionColumns)}")
    lines += [
        f"- Location: {doc.uri}",
        f"- Profiled at: {doc.updatedAt}",
        *([f"- Delta commits: {doc.commitCount:,} in total"] if doc.commitCount is not None else []),
        *_freshness_lines(doc.freshness),
        f"- Full JSON: [{posixpath.basename(table_json_path(fqn))}]({_link(table_json_path(fqn), here, base_url)})",
        f"- Catalogue index: [llms.txt]({_link('llms.txt', here, base_url)})",
        "",
        "## Schema",
        "",
    ]
    documented = any(c.description or c.tags for c in doc.columns)
    lines += _table(
        ["Column", "Type", "Nullable", "Partition", *(["Description"] if documented else [])],
        [
            [c.name, c.dataType, "yes" if c.nullable else "no", "yes" if c.partitioned else "",
             *([_column_description(c)] if documented else [])]
            for c in doc.columns
        ],
    )

    profiles = {p.name: p for p in doc.tableProfile.columnProfile}
    stat_rows = []
    for c in doc.columns:
        p = profiles.get(c.name)
        if p is None:
            continue
        top = f"{p.top} ({p.freq:,})" if p.top is not None and p.freq is not None else p.top
        stat_rows.append([c.name, p.nullCount, p.uniqueCount, p.min, p.mean, p.max, top])
    if stat_rows:
        lines += ["", "## Statistics", ""]
        lines += _table(["Column", "Nulls", "Distinct", "Min", "Mean", "Max", "Most common"], stat_rows)

    distributions = [(c.name, profiles[c.name].distribution) for c in doc.columns
                     if c.name in profiles and profiles[c.name].distribution]
    if distributions:
        lines += ["", "## Time distribution"]
        for column, dist in distributions:
            lines += _distribution_lines(column, dist, doc.updatedAt)

    if doc.sampleData and doc.sampleData.rows:
        lines += ["", "## Sample rows", ""]
        lines += _table(doc.sampleData.columns, doc.sampleData.rows)

    history = (doc.extension or {}).get("deltaHistory") or []
    if history:
        lines += ["", "## Recent changes", ""]
        if doc.commitCount is not None:
            lines += [f"Latest {min(len(history), RECENT_HISTORY_COUNT)} of {doc.commitCount:,} commits:", ""]
        lines += _table(
            ["Version", "Timestamp", "Operation", "Description"],
            [[h.version, h.timestamp, h.operation, h.description] for h in history[:RECENT_HISTORY_COUNT]],
        )

    if related:
        group = group_of(fqn)
        lines += ["", f"## Other tables in {group}", ""]
        for entry in sorted(related, key=lambda e: e.fullyQualifiedName):
            link = _link(table_md_path(entry.fullyQualifiedName), here, base_url)
            suffix = f": {_inline(entry.description)}" if entry.description else ""
            lines.append(f"- [{entry.fullyQualifiedName}]({link}){suffix}")

    return "\n".join(lines) + "\n"
