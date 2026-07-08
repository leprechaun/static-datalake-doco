import json

import deltalake
import polars as pl
import pytest
from typer.testing import CliRunner

from datalake_doco.cli import app

runner = CliRunner()


def _write(path, df=None):
    path.mkdir(parents=True, exist_ok=True)
    if df is None:
        df = pl.DataFrame({"x": pl.Series([1, 2, 3], dtype=pl.Int64)})
    deltalake.write_deltalake(str(path), df)


def _invoke(args):
    return runner.invoke(app, args, catch_exceptions=False)


# ── Basic smoke ───────────────────────────────────────────────────────────────

def test_generate_exits_zero(tmp_path):
    _write(tmp_path / "events")
    out = tmp_path / "out"
    result = _invoke(["generate", str(tmp_path), "--output", str(out), "--workers", "1"])
    assert result.exit_code == 0


def test_generate_creates_catalog_and_table_doc(tmp_path):
    _write(tmp_path / "events")
    out = tmp_path / "out"
    _invoke(["generate", str(tmp_path), "--output", str(out), "--workers", "1"])
    assert (out / "catalog.json").exists()
    assert (out / "tables" / "events.json").exists()


# ── Multi-URI merge ───────────────────────────────────────────────────────────

def test_generate_merges_multiple_uris(tmp_path):
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    _write(root_a / "sales")
    _write(root_b / "users")
    out = tmp_path / "out"

    _invoke(["generate", str(root_a), str(root_b), "--output", str(out), "--workers", "1"])

    catalog = json.loads((out / "catalog.json").read_text())
    names = {t["name"] for t in catalog["tables"]}
    assert names == {"sales", "users"}


def test_catalog_sources_lists_all_input_uris(tmp_path):
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    _write(root_a / "t1")
    _write(root_b / "t2")
    out = tmp_path / "out"

    _invoke(["generate", str(root_a), str(root_b), "--output", str(out), "--workers", "1"])

    catalog = json.loads((out / "catalog.json").read_text())
    assert str(root_a) in catalog["sources"]
    assert str(root_b) in catalog["sources"]


# ── Sample data exclusion ─────────────────────────────────────────────────────

def test_excluded_table_has_no_sample_data(tmp_path):
    _write(tmp_path / "events")
    out = tmp_path / "out"

    _invoke([
        "generate", str(tmp_path), "--output", str(out),
        "--sample-data-count", "5",
        "--sample-data-exclude-tables", "events",
        "--workers", "1",
    ])

    doc = json.loads((out / "tables" / "events.json").read_text())
    assert doc["sampleData"] is None


def test_excluded_table_still_appears_in_catalog(tmp_path):
    _write(tmp_path / "events")
    out = tmp_path / "out"

    _invoke([
        "generate", str(tmp_path), "--output", str(out),
        "--sample-data-count", "5",
        "--sample-data-exclude-tables", "events",
        "--workers", "1",
    ])

    catalog = json.loads((out / "catalog.json").read_text())
    assert any(t["name"] == "events" for t in catalog["tables"])


def test_non_excluded_table_has_sample_data(tmp_path):
    _write(tmp_path / "events")
    _write(tmp_path / "users")
    out = tmp_path / "out"

    _invoke([
        "generate", str(tmp_path), "--output", str(out),
        "--sample-data-count", "3",
        "--sample-data-exclude-tables", "events",
        "--workers", "1",
    ])

    doc = json.loads((out / "tables" / "users.json").read_text())
    assert doc["sampleData"] is not None
    assert len(doc["sampleData"]["rows"]) == 3


def test_exclusion_matches_fullyqualifiedname_with_dots(tmp_path):
    """Exclusion list uses dots; scanner returns slash-separated names."""
    _write(tmp_path / "bronze" / "events")
    out = tmp_path / "out"

    _invoke([
        "generate", str(tmp_path), "--output", str(out),
        "--sample-data-count", "5",
        "--sample-data-exclude-tables", "bronze.events",
        "--workers", "1",
    ])

    doc = json.loads((out / "tables" / "bronze" / "events.json").read_text())
    assert doc["sampleData"] is None


# ── Failed table handling ─────────────────────────────────────────────────────

def test_failed_table_is_skipped(tmp_path):
    """A directory that looks like a Delta table but isn't readable should be
    skipped, not crash the run."""
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "_delta_log").mkdir()  # triggers scanner, fails on read

    _write(tmp_path / "valid")
    out = tmp_path / "out"

    result = runner.invoke(app, [
        "generate", str(tmp_path), "--output", str(out), "--workers", "1"
    ])

    assert result.exit_code == 0
    catalog = json.loads((out / "catalog.json").read_text())
    names = {t["name"] for t in catalog["tables"]}
    assert "valid" in names
    assert "broken" not in names


def test_failed_table_error_goes_to_stderr(tmp_path):
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "_delta_log").mkdir()
    out = tmp_path / "out"

    result = runner.invoke(app, [
        "generate", str(tmp_path), "--output", str(out), "--workers", "1"
    ])

    assert "[error]" in result.output
