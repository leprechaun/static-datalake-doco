"""Render the catalogue as Markdown for LLMs: an llms.txt index plus one file per table."""

import posixpath

from datalake_doco.models import Catalog, CatalogEntry, TableDoc

RECENT_HISTORY_COUNT = 5


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


def render_llms_txt(catalog: Catalog, base_url: str | None = None) -> str:
    lines = [
        "# Datalake catalogue",
        "",
        (
            f"> {len(catalog.tables)} Delta Lake tables from {', '.join(catalog.sources)}. "
            f"Generated {catalog.generatedAt}. "
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
            if entry.description:
                summary = f"{_inline(entry.description)} ({summary})"
            lines.append(f"- [{entry.fullyQualifiedName}]({link}): {summary}")

    return "\n".join(lines) + "\n"


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
        f"- Full JSON: [{posixpath.basename(table_json_path(fqn))}]({_link(table_json_path(fqn), here, base_url)})",
        f"- Catalogue index: [llms.txt]({_link('llms.txt', here, base_url)})",
        "",
        "## Schema",
        "",
    ]
    lines += _table(
        ["Column", "Type", "Nullable", "Partition"],
        [
            [c.name, c.dataType, "yes" if c.nullable else "no", "yes" if c.partitioned else ""]
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

    if doc.sampleData and doc.sampleData.rows:
        lines += ["", "## Sample rows", ""]
        lines += _table(doc.sampleData.columns, doc.sampleData.rows)

    history = (doc.extension or {}).get("deltaHistory") or []
    if history:
        lines += ["", "## Recent changes", ""]
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
