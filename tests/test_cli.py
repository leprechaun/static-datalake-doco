import json

import pytest
from typer.testing import CliRunner

from conftest import FIXED_TS
from datalake_doco.cli import app
from datalake_doco.models import Column, ColumnProfile, SampleData, TableDoc, TableProfile
from datalake_doco.readers.delta import DeltaReader

runner = CliRunner()


def _make_table(path):
    """Create a minimal directory the scanner recognises as a Delta table."""
    path.mkdir(parents=True, exist_ok=True)
    (path / "_delta_log").mkdir()


def _fake_doc(name, uri, sample_count=0):
    parts = name.split("/")
    col = Column(name="x", dataType="BIGINT", nullable=True, ordinalPosition=1)
    profile = ColumnProfile(name="x", timestamp=FIXED_TS, valuesCount=3.0, nullCount=0.0)
    sample = SampleData(columns=["x"], rows=[[1], [2], [3]]) if sample_count > 0 else None
    return TableDoc(
        name=parts[-1],
        fullyQualifiedName=".".join(parts),
        uri=uri,
        updatedAt=FIXED_TS,
        columns=[col],
        tableProfile=TableProfile(
            timestamp=FIXED_TS, rowCount=3, columnCount=1, columnProfile=[profile]
        ),
        partitionColumns=[],
        sampleData=sample,
    )


@pytest.fixture(autouse=True)
def mock_reader(monkeypatch):
    """Replace DeltaReader.read with a fake that returns minimal TableDoc objects.

    Tables whose name or URI contains 'broken' raise RuntimeError, which the
    CLI catches and skips — matching production error-handling behaviour.
    """
    def _read(self, uri, name, sample_count=0, **_):
        if "broken" in name or "broken" in uri:
            raise RuntimeError("Simulated read failure")
        return _fake_doc(name, uri, sample_count)

    monkeypatch.setattr(DeltaReader, "read", _read)


def _invoke(*args):
    return runner.invoke(app, list(args), catch_exceptions=False)


# ── Basic smoke ───────────────────────────────────────────────────────────────

def test_generate_exits_zero(tmp_path):
    _make_table(tmp_path / "events")
    result = _invoke("generate", str(tmp_path), "--output", str(tmp_path / "out"))
    assert result.exit_code == 0


def test_generate_creates_catalog_and_table_doc(tmp_path):
    _make_table(tmp_path / "events")
    out = tmp_path / "out"
    _invoke("generate", str(tmp_path), "--output", str(out))
    assert (out / "catalog.json").exists()
    assert (out / "tables" / "events.json").exists()


# ── Multi-URI merge ───────────────────────────────────────────────────────────

def test_generate_merges_multiple_uris(tmp_path):
    root_a, root_b = tmp_path / "a", tmp_path / "b"
    _make_table(root_a / "sales")
    _make_table(root_b / "users")
    out = tmp_path / "out"
    _invoke("generate", str(root_a), str(root_b), "--output", str(out))
    catalog = json.loads((out / "catalog.json").read_text())
    assert {t["name"] for t in catalog["tables"]} == {"sales", "users"}


def test_catalog_sources_lists_all_input_uris(tmp_path):
    root_a, root_b = tmp_path / "a", tmp_path / "b"
    _make_table(root_a / "t1")
    _make_table(root_b / "t2")
    out = tmp_path / "out"
    _invoke("generate", str(root_a), str(root_b), "--output", str(out))
    sources = json.loads((out / "catalog.json").read_text())["sources"]
    assert str(root_a) in sources
    assert str(root_b) in sources


# ── Sample data exclusion ─────────────────────────────────────────────────────

def test_excluded_table_has_no_sample_data(tmp_path):
    _make_table(tmp_path / "events")
    out = tmp_path / "out"
    _invoke("generate", str(tmp_path), "--output", str(out),
            "--sample-data-count", "5", "--sample-data-exclude-tables", "events")
    doc = json.loads((out / "tables" / "events.json").read_text())
    assert doc["sampleData"] is None


def test_excluded_table_still_appears_in_catalog(tmp_path):
    _make_table(tmp_path / "events")
    out = tmp_path / "out"
    _invoke("generate", str(tmp_path), "--output", str(out),
            "--sample-data-count", "5", "--sample-data-exclude-tables", "events")
    catalog = json.loads((out / "catalog.json").read_text())
    assert any(t["name"] == "events" for t in catalog["tables"])


def test_non_excluded_table_has_sample_data(tmp_path):
    _make_table(tmp_path / "events")
    _make_table(tmp_path / "users")
    out = tmp_path / "out"
    _invoke("generate", str(tmp_path), "--output", str(out),
            "--sample-data-count", "3", "--sample-data-exclude-tables", "events")
    doc = json.loads((out / "tables" / "users.json").read_text())
    assert doc["sampleData"] is not None
    assert len(doc["sampleData"]["rows"]) == 3


def test_exclusion_matches_fullyqualifiedname_with_dots(tmp_path):
    """Exclusion list uses dots; scanner returns slash-separated names."""
    _make_table(tmp_path / "bronze" / "events")
    out = tmp_path / "out"
    _invoke("generate", str(tmp_path), "--output", str(out),
            "--sample-data-count", "5", "--sample-data-exclude-tables", "bronze.events")
    doc = json.loads((out / "tables" / "bronze" / "events.json").read_text())
    assert doc["sampleData"] is None


# ── Failed table handling ─────────────────────────────────────────────────────

def test_failed_table_is_skipped(tmp_path):
    _make_table(tmp_path / "broken")
    _make_table(tmp_path / "valid")
    out = tmp_path / "out"
    result = runner.invoke(app, ["generate", str(tmp_path), "--output", str(out)])
    assert result.exit_code == 0
    names = {t["name"] for t in json.loads((out / "catalog.json").read_text())["tables"]}
    assert "valid" in names
    assert "broken" not in names


def test_failed_table_error_message_in_output(tmp_path):
    _make_table(tmp_path / "broken")
    out = tmp_path / "out"
    result = runner.invoke(app, ["generate", str(tmp_path), "--output", str(out)])
    assert "[error]" in result.output
