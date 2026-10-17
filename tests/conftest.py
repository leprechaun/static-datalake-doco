import os
from unittest.mock import MagicMock

# Cap polars and rayon thread pools to 1 so tests don't compete for cores.
os.environ.setdefault("POLARS_MAX_THREADS", "1")
os.environ.setdefault("RAYON_NUM_THREADS", "1")

FIXED_TS = "2026-01-01T00:00:00+00:00"

DEFAULT_HISTORY = [
    {
        "version": 0,
        "timestamp": 1704067200000,
        "operation": "WRITE",
        "operationParameters": {"mode": "Overwrite"},
    }
]


def make_field(name, nullable=True):
    """Build a mock DeltaTable schema field."""
    f = MagicMock()
    f.name = name
    f.nullable = nullable
    return f


def make_mock_dt(fields, partition_columns=None, history=None):
    """Build a mock DeltaTable with sensible defaults."""
    dt = MagicMock()

    schema = MagicMock()
    schema.fields = fields
    dt.schema.return_value = schema

    metadata = MagicMock()
    metadata.partition_columns = partition_columns if partition_columns is not None else []
    dt.metadata.return_value = metadata

    dt.history.return_value = history if history is not None else DEFAULT_HISTORY

    return dt
