from conftest import FIXED_TS
from test_writer import make_catalog_entry, make_column, make_profile, make_table_doc

from datalake_doco.markdown import render_llms_txt, render_table_md
from datalake_doco.models import Catalog, HistoryEntry, SampleData, TableProfile
from datalake_doco.writer import write_output


def _catalog(*docs):
    return Catalog(generatedAt=FIXED_TS, sources=["s3://lake"], tables=[make_catalog_entry(d) for d in docs])


def _doc(fqn, description=None, **overrides):
    entry_doc = make_table_doc(name=fqn.split(".")[-1], fullyQualifiedName=fqn, **overrides)
    entry_doc.description = description
    return entry_doc


def _entry(fqn, description=None):
    entry = make_catalog_entry(_doc(fqn))
    entry.description = description
    return entry


# ── llms.txt ──────────────────────────────────────────────────────────────────

def test_llms_txt_groups_tables_by_source_and_layer():
    text = render_llms_txt(_catalog(_doc("src.bronze.events"), _doc("src.gold.daily")))
    assert "## src.bronze" in text
    assert "## src.gold" in text


def test_llms_txt_links_are_relative_by_default():
    text = render_llms_txt(_catalog(_doc("src.bronze.events")))
    assert "- [src.bronze.events](tables/src/bronze/events.md): 3 rows, 1 columns" in text


def test_llms_txt_links_use_base_url():
    text = render_llms_txt(_catalog(_doc("src.bronze.events")), base_url="https://docs.example/lake/")
    assert "(https://docs.example/lake/tables/src/bronze/events.md)" in text


def test_llms_txt_includes_description():
    catalog = Catalog(generatedAt=FIXED_TS, sources=["s3://lake"], tables=[_entry("src.bronze.events", "Raw clicks")])
    assert "events.md): Raw clicks (3 rows, 1 columns)" in render_llms_txt(catalog)


FRESHNESS = {
    "lastWrite": "2026-11-01T13:02:22+00:00", "secondsSinceLastWrite": 5 * 86400,
    "typicalIntervalSeconds": 2 * 3600, "intervalGaps": 49, "burstGapSeconds": 60, "dataCommits": 1238, "ratio": 60.0,
}


def test_llms_txt_freshness_hint():
    entry = _entry("src.bronze.events")
    entry.freshness = FRESHNESS
    text = render_llms_txt(Catalog(generatedAt=FIXED_TS, sources=["s3://lake"], tables=[entry]))
    assert "events.md): 3 rows, 1 columns; last write 5.0 days ago, 60× its typical 2.0 h interval" in text


def test_llms_txt_freshness_hint_single_write():
    entry = _entry("src.bronze.events")
    entry.freshness = {**FRESHNESS, "typicalIntervalSeconds": None, "ratio": None, "dataCommits": 1, "secondsSinceLastWrite": 600}
    text = render_llms_txt(Catalog(generatedAt=FIXED_TS, sources=["s3://lake"], tables=[entry]))
    assert "; last write 10 min ago, 1 write in total" in text


def test_llms_txt_freshness_hint_sub_second_interval():
    entry = _entry("src.bronze.events")
    entry.freshness = {**FRESHNESS, "secondsSinceLastWrite": 214, "typicalIntervalSeconds": 0.4, "ratio": 535.0}
    text = render_llms_txt(Catalog(generatedAt=FIXED_TS, sources=["s3://lake"], tables=[entry]))
    assert "; last write 3.6 min ago, 535× its typical 0.4 s interval" in text


# ── Table Markdown ────────────────────────────────────────────────────────────

def test_table_md_has_description_and_schema():
    doc = _doc("src.bronze.events", description="Raw clicks\none row per click")
    text = render_table_md(doc, [])
    assert text.startswith("# src.bronze.events\n")
    assert "> Raw clicks\n> one row per click" in text
    assert "| id | BIGINT | yes |  |" in text


def test_table_md_freshness_lines():
    text = render_table_md(_doc("src.bronze.events", freshness=FRESHNESS), [])
    assert "- Last data write: 2026-11-01T13:02:22+00:00 (5.0 days before profiling)" in text
    assert ("- Typical write interval: 2.0 h (median of the last 49 gaps between data writes; "
            "writes under 60 s apart count as one burst); the time since the last write is 60× that") in text


def test_table_md_freshness_without_burst_collapsing():
    freshness = {**FRESHNESS, "typicalIntervalSeconds": 10, "intervalGaps": 49, "burstGapSeconds": None}
    text = render_table_md(_doc("src.bronze.events", freshness=freshness), [])
    assert "- Typical write interval: 10 s (median of the last 49 gaps between data writes);" in text


def test_table_md_without_data_writes():
    assert "- Last data write: none in the Delta history" in render_table_md(_doc("src.bronze.events"), [])


def test_table_md_statistics():
    doc = _doc("src.bronze.events")
    doc.tableProfile = TableProfile(
        timestamp=FIXED_TS, rowCount=3, columnCount=1,
        columnProfile=[make_profile(nullCount=1.0, min=1.0, mean=2.5, max=4.0)],
    )
    assert "| id | 1 |  | 1 | 2.5 | 4 |  |" in render_table_md(doc, [])


def test_table_md_statistics_temporal_min_max():
    doc = _doc("src.bronze.events")
    doc.tableProfile = TableProfile(
        timestamp=FIXED_TS, rowCount=3, columnCount=1,
        columnProfile=[make_profile(nullCount=0.0, min="2024-01-01", max="2024-03-31")],
    )
    assert "| id | 0 |  | 2024-01-01 |  | 2024-03-31 |  |" in render_table_md(doc, [])


def _dist(**overrides):
    dist = {
        "grain": "sub-daily", "bucketing": "UTC",
        "partialDay": "2026-11-06", "partialMonth": "2026-11",
        "daysWithData": 3, "missingDays": 41,
        "largestGap": {"start": "2026-09-02", "end": "2026-10-10", "days": 39},
        "gaps": [
            {"start": "2026-09-02", "end": "2026-10-10", "count": 39},
            {"start": "2026-11-04", "end": "2026-11-05", "count": 2},
        ],
        "rowsPerDay": {"min": 100, "p5": 105.5, "median": 1200, "p95": 1180, "max": 1200},
        "year": {"2026": 1310},
        "month": {"2026-09": 1200, "2026-10": 100, "2026-11": 10},
        "day": {"2026-09-01": 1200, "2026-10-11": 100, "2026-11-06": 10},
        "weekday": {"Mon": 0, "Tue": 1200, "Wed": 0, "Thu": 0, "Fri": 10, "Sat": 0, "Sun": 100},
        "hour": {f"{h:02d}": (1310 if h == 7 else 0) for h in range(24)},
    }
    dist.update(overrides)
    return dist


def _doc_with(*profiles):
    doc = _doc("src.bronze.events", columns=[make_column(name=p.name) for p in profiles])
    doc.tableProfile = TableProfile(timestamp=FIXED_TS, rowCount=1310, columnCount=len(profiles), columnProfile=list(profiles))
    return doc


def test_table_md_time_distribution():
    text = render_table_md(_doc_with(make_profile(distribution=_dist())), [])
    assert "## Time distribution\n\n### id (sub-daily)\n\nBucketed in UTC. Data on 3 days from 2026-09-01 to 2026-11-06.\n" in text
    assert "- Rows per day (days with data, excluding the partial day 2026-11-06): min 100, p5 106, median 1,200, p95 1,180, max 1,200" in text
    assert "- Missing days: 41, in 2 gaps (largest first):\n  - 2026-09-02 to 2026-10-10 (39 days)\n  - 2026-11-04 to 2026-11-05 (2 days)" in text
    assert "| 2026 |  |  |  |  |  |  |  |  | 1,200 | 100 | 10\\* |  | 1,310 |" in text
    assert f"\\* Partial period: still in progress when profiled at {FIXED_TS}." in text
    assert "| Mon | Tue | Wed | Thu | Fri | Sat | Sun |" in text
    assert "Rows by hour of day:" in text


def test_table_md_single_day_gap_and_singular_units():
    dist = _dist(gaps=[{"start": "2026-10-01", "end": "2026-10-01", "count": 1}])
    text = render_table_md(_doc_with(make_profile(distribution=dist)), [])
    assert "- Missing days: 1, in 1 gap (largest first):\n  - 2026-10-01 (1 day)" in text


def test_table_md_caps_gap_list():
    gaps = [{"start": f"2026-0{m}-10", "end": f"2026-0{m}-10", "count": 1} for m in range(1, 9)]
    text = render_table_md(_doc_with(make_profile(distribution=_dist(gaps=gaps))), [])
    assert "  - 2026-05-10 (1 day)" in text
    assert "  - 2026-06-10 (1 day)" not in text
    assert "  - … 3 more gaps (3 days)" in text


def test_table_md_monthly_column():
    dist = _dist(grain="monthly", bucketing="date", gaps=[], partialMonth="2027-01")
    text = render_table_md(_doc_with(make_profile(distribution=dist)), [])
    assert "### id (monthly)\n\nDates, bucketed as stored. Data in 3 months from 2026-09 to 2026-11.\n\n- Missing months: none." in text
    assert "Rows by weekday" not in text
    assert "Rows per day" not in text
    assert "Partial period" not in text


def test_table_md_naive_bucketing_label():
    text = render_table_md(_doc_with(make_profile(distribution=_dist(bucketing="naive"))), [])
    assert "Naive timestamps, bucketed as stored." in text


def test_table_md_duplicate_columns_collapse_to_one_line():
    text = render_table_md(_doc_with(
        make_profile(name="timestamp", distribution=_dist()),
        make_profile(name="date", distribution=_dist(sameAs={"column": "timestamp", "relation": "derived"})),
        make_profile(name="arrived_at", distribution=_dist(sameAs={"column": "timestamp", "relation": "identical"})),
    ), [])
    assert "`date`: same per-day counts as `timestamp` (derived)." in text
    assert "`arrived_at`: identical per-day counts to `timestamp`." in text
    assert "### date" not in text


def test_table_md_omits_time_distribution_when_absent():
    assert "## Time distribution" not in render_table_md(_doc("src.bronze.events"), [])


def test_table_md_sample_rows_escape_pipes():
    doc = _doc("src.bronze.events", sampleData=SampleData(columns=["id"], rows=[["a|b"]]))
    assert "| a\\|b |" in render_table_md(doc, [])


def test_table_md_recent_changes_capped():
    history = [HistoryEntry(version=v, timestamp=FIXED_TS, operation="WRITE", parameters={}, description=None, engine_info=None)
               for v in range(10, 0, -1)]
    text = render_table_md(_doc("src.bronze.events", extension={"deltaHistory": history}), [])
    assert "| 10 |" in text
    assert "| 6 |" in text
    assert "| 5 |" not in text


def test_table_md_commit_count():
    history = [HistoryEntry(version=v, timestamp=FIXED_TS, operation="WRITE", parameters={}, description=None, engine_info=None)
               for v in range(84141, 84131, -1)]
    text = render_table_md(_doc("src.bronze.events", extension={"deltaHistory": history}, commitCount=84142), [])
    assert "- Delta commits: 84,142 in total" in text
    assert "## Recent changes\n\nLatest 5 of 84,142 commits:\n" in text


def test_table_md_related_links_are_relative_to_the_file():
    text = render_table_md(_doc("src.bronze.events"), [_entry("src.bronze.clicks", "Click stream")])
    assert "## Other tables in src.bronze" in text
    assert "- [src.bronze.clicks](clicks.md): Click stream" in text
    assert "[llms.txt](../../../llms.txt)" in text
    assert "[events.json](events.json)" in text


def test_table_md_related_links_use_base_url():
    text = render_table_md(_doc("src.bronze.events"), [_entry("src.bronze.clicks")], base_url="https://docs.example")
    assert "(https://docs.example/tables/src/bronze/clicks.md)" in text


def test_table_md_without_related_has_no_section():
    assert "Other tables" not in render_table_md(_doc("src.bronze.events"), [])


def test_table_md_lists_partition_columns():
    doc = _doc("src.bronze.events", partitionColumns=["day"], columns=[make_column(partitioned=True)])
    assert "- Partitioned by: day" in render_table_md(doc, [])


# ── Writer ────────────────────────────────────────────────────────────────────

def test_write_output_links_tables_in_the_same_group_only(tmp_path):
    docs = [_doc("src.bronze.events"), _doc("src.bronze.clicks"), _doc("src.gold.daily")]
    write_output(_catalog(*docs), docs, tmp_path)
    assert (tmp_path / "llms.txt").exists()
    events = (tmp_path / "tables/src/bronze/events.md").read_text()
    assert "src.bronze.clicks" in events
    assert "src.gold.daily" not in events
    assert "Other tables" not in (tmp_path / "tables/src/gold/daily.md").read_text()
