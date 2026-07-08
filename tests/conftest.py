import multiprocessing
import os

# Use spawn instead of fork so child processes start with a clean Rust/Rayon
# runtime. Fork inherits an already-initialised thread pool from the parent,
# which deadlocks or corrupts state in polars/deltalake workers.
multiprocessing.set_start_method("spawn", force=True)

# Cap polars and rayon thread pools to 1 so tests don't compete for cores.
os.environ.setdefault("POLARS_MAX_THREADS", "1")
os.environ.setdefault("RAYON_NUM_THREADS", "1")

import deltalake
import polars as pl
import pytest


@pytest.fixture
def numeric_table(tmp_path):
    """Delta table with two numeric columns, 5 rows, no nulls."""
    df = pl.DataFrame({
        "id": pl.Series([1, 2, 3, 4, 5], dtype=pl.Int64),
        "value": pl.Series([10.0, 20.0, 30.0, 40.0, 50.0], dtype=pl.Float64),
    })
    path = str(tmp_path / "numeric")
    deltalake.write_deltalake(path, df)
    return path


@pytest.fixture
def mixed_table(tmp_path):
    """Delta table with numeric and string columns."""
    df = pl.DataFrame({
        "id": pl.Series([1, 2, 3], dtype=pl.Int32),
        "name": pl.Series(["alice", "bob", "alice"], dtype=pl.String),
        "score": pl.Series([1.5, 2.5, 3.5], dtype=pl.Float64),
    })
    path = str(tmp_path / "mixed")
    deltalake.write_deltalake(path, df)
    return path


@pytest.fixture
def nullable_table(tmp_path):
    """Delta table where every column has at least one null."""
    df = pl.DataFrame({
        "x": pl.Series([1.0, None, 3.0], dtype=pl.Float64),
        "label": pl.Series(["a", None, "a"], dtype=pl.String),
    })
    path = str(tmp_path / "nullable")
    deltalake.write_deltalake(path, df)
    return path
