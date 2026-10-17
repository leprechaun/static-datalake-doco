import pytest

from datalake_doco.scanner import scan


def _make_table(path):
    """Create a minimal directory the scanner recognises as a Delta table."""
    path.mkdir(parents=True, exist_ok=True)
    (path / "_delta_log").mkdir()


# ── Discovery ─────────────────────────────────────────────────────────────────

def test_finds_single_table(tmp_path):
    _make_table(tmp_path / "events")
    assert len(scan(str(tmp_path))) == 1


def test_ignores_plain_directory(tmp_path):
    (tmp_path / "notadelta").mkdir()
    assert scan(str(tmp_path)) == []


def test_ignores_files_in_directory(tmp_path):
    (tmp_path / "data.csv").write_text("a,b\n1,2")
    assert scan(str(tmp_path)) == []


def test_finds_multiple_tables(tmp_path):
    for name in ("alpha", "beta", "gamma"):
        _make_table(tmp_path / name)
    assert len(scan(str(tmp_path))) == 3


def test_finds_nested_tables(tmp_path):
    _make_table(tmp_path / "bronze" / "events")
    _make_table(tmp_path / "silver" / "events")
    assert len(scan(str(tmp_path))) == 2


# ── Name derivation ───────────────────────────────────────────────────────────

def test_name_is_relative_to_root(tmp_path):
    _make_table(tmp_path / "events")
    _, name = scan(str(tmp_path))[0]
    assert name == "events"


def test_nested_name_preserves_path_segments(tmp_path):
    _make_table(tmp_path / "bronze" / "events")
    _, name = scan(str(tmp_path))[0]
    assert name == "bronze/events"


def test_deeply_nested_name(tmp_path):
    _make_table(tmp_path / "mydb" / "bronze" / "raw_events")
    _, name = scan(str(tmp_path))[0]
    assert name == "mydb/bronze/raw_events"


# ── Does not recurse into Delta internals ─────────────────────────────────────

def test_does_not_recurse_into_delta_table(tmp_path):
    _make_table(tmp_path / "events")
    # add a nested directory inside the table — should NOT count as a second table
    (tmp_path / "events" / "partition=a" / "_delta_log").mkdir(parents=True)
    assert len(scan(str(tmp_path))) == 1


def test_does_not_return_intermediate_directories_as_tables(tmp_path):
    _make_table(tmp_path / "a" / "b")
    names = [name for _, name in scan(str(tmp_path))]
    assert "a" not in names


# ── Trailing slash tolerance ──────────────────────────────────────────────────

def test_trailing_slash_in_root_uri(tmp_path):
    _make_table(tmp_path / "events")
    assert len(scan(str(tmp_path) + "/")) == 1
