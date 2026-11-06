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


# ── Table Markdown ────────────────────────────────────────────────────────────

def test_table_md_has_description_and_schema():
    doc = _doc("src.bronze.events", description="Raw clicks\none row per click")
    text = render_table_md(doc, [])
    assert text.startswith("# src.bronze.events\n")
    assert "> Raw clicks\n> one row per click" in text
    assert "| id | BIGINT | yes |  |" in text


def test_table_md_statistics():
    doc = _doc("src.bronze.events")
    doc.tableProfile = TableProfile(
        timestamp=FIXED_TS, rowCount=3, columnCount=1,
        columnProfile=[make_profile(nullCount=1.0, min=1.0, mean=2.5, max=4.0)],
    )
    assert "| id | 1 |  | 1 | 2.5 | 4 |  |" in render_table_md(doc, [])


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
