import deltalake
import polars as pl
import pytest

from datalake_doco.scanner import scan


def _write(path):
    path.mkdir(parents=True, exist_ok=True)
    deltalake.write_deltalake(str(path), pl.DataFrame({"x": pl.Series([1], dtype=pl.Int64)}))


# ── Discovery ─────────────────────────────────────────────────────────────────

def test_finds_single_table(tmp_path):
    _write(tmp_path / "events")
    results = scan(str(tmp_path))
    assert len(results) == 1


def test_ignores_plain_directory(tmp_path):
    (tmp_path / "notadelta").mkdir()
    results = scan(str(tmp_path))
    assert results == []


def test_ignores_files_in_directory(tmp_path):
    (tmp_path / "data.csv").write_text("a,b\n1,2")
    results = scan(str(tmp_path))
    assert results == []


def test_finds_multiple_tables(tmp_path):
    for name in ("alpha", "beta", "gamma"):
        _write(tmp_path / name)
    results = scan(str(tmp_path))
    assert len(results) == 3


def test_finds_nested_tables(tmp_path):
    _write(tmp_path / "bronze" / "events")
    _write(tmp_path / "silver" / "events")
    results = scan(str(tmp_path))
    assert len(results) == 2


# ── Name derivation ───────────────────────────────────────────────────────────

def test_name_is_relative_to_root(tmp_path):
    _write(tmp_path / "events")
    _, name = scan(str(tmp_path))[0]
    assert name == "events"


def test_nested_name_preserves_path_segments(tmp_path):
    _write(tmp_path / "bronze" / "events")
    _, name = scan(str(tmp_path))[0]
    assert name == "bronze/events"


def test_deeply_nested_name(tmp_path):
    _write(tmp_path / "mydb" / "bronze" / "raw_events")
    _, name = scan(str(tmp_path))[0]
    assert name == "mydb/bronze/raw_events"


def test_uri_is_absolute_path(tmp_path):
    _write(tmp_path / "events")
    uri, _ = scan(str(tmp_path))[0]
    assert "events" in uri


# ── Does not recurse into Delta internals ─────────────────────────────────────

def test_partitioned_table_counts_as_one(tmp_path):
    path = str(tmp_path / "events")
    df = pl.DataFrame({
        "x": pl.Series([1, 2], dtype=pl.Int64),
        "p": pl.Series(["a", "b"], dtype=pl.String),
    })
    deltalake.write_deltalake(path, df, partition_by=["p"])
    results = scan(str(tmp_path))
    assert len(results) == 1


def test_does_not_return_intermediate_directories_as_tables(tmp_path):
    _write(tmp_path / "a" / "b")
    results = scan(str(tmp_path))
    names = [name for _, name in results]
    assert "a" not in names


# ── Trailing slash tolerance ──────────────────────────────────────────────────

def test_trailing_slash_in_root_uri(tmp_path):
    _write(tmp_path / "events")
    results = scan(str(tmp_path) + "/")
    assert len(results) == 1
