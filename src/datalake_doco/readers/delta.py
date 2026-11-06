from datetime import UTC, datetime
from typing import Any

import deltalake
import polars as pl

from datalake_doco.freshness import freshness
from datalake_doco.models import (
    Column,
    ColumnProfile,
    HistoryEntry,
    SampleData,
    TableDoc,
    TableProfile,
)
from datalake_doco.profiler import profile


def _polars_type(dtype: pl.DataType) -> tuple[str, int | None, int | None]:
    """Return (dataType, precision, scale) for an OpenMetadata column."""
    mapping = {
        pl.Int8: ("TINYINT", None, None),
        pl.Int16: ("SMALLINT", None, None),
        pl.Int32: ("INT", None, None),
        pl.Int64: ("BIGINT", None, None),
        pl.UInt8: ("TINYINT", None, None),
        pl.UInt16: ("SMALLINT", None, None),
        pl.UInt32: ("INT", None, None),
        pl.UInt64: ("BIGINT", None, None),
        pl.Float32: ("FLOAT", None, None),
        pl.Float64: ("DOUBLE", None, None),
        pl.Boolean: ("BOOLEAN", None, None),
        pl.String: ("STRING", None, None),
        pl.Utf8: ("STRING", None, None),
        pl.Date: ("DATE", None, None),
        pl.Binary: ("BINARY", None, None),
    }
    for cls, result in mapping.items():
        if isinstance(dtype, cls):
            return result
    if isinstance(dtype, pl.Datetime):
        return ("TIMESTAMP", None, None)
    if isinstance(dtype, pl.Decimal):
        return ("DECIMAL", dtype.precision, dtype.scale)
    if isinstance(dtype, (pl.List, pl.Array)):
        return ("ARRAY", None, None)
    if isinstance(dtype, pl.Struct):
        return ("STRUCT", None, None)
    return (str(dtype).upper(), None, None)


# Field metadata keys that hold a column's description: our own, then Spark's convention.
DESCRIPTION_KEYS = ("description", "comment")
# Field metadata written by Delta and Spark themselves (column mapping ids, generated-column
# expressions, char/varchar lengths), not by whoever documented the table.
INTERNAL_KEY_PREFIXES = ("delta.", "__")


def _column_metadata(metadata: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    """Split a Delta field's metadata into its description and the remaining tags (e.g. unit)."""
    description = next((metadata[k] for k in DESCRIPTION_KEYS if metadata.get(k)), None)
    tags = {
        k: v for k, v in metadata.items()
        if k not in DESCRIPTION_KEYS and not k.startswith(INTERNAL_KEY_PREFIXES)
    }
    return (str(description) if description is not None else None), tags


def _parse_history(raw: list[dict]) -> list[HistoryEntry]:
    entries = []
    for item in raw:
        ts = item.get("timestamp")
        if isinstance(ts, (int, float)):
            ts = datetime.fromtimestamp(ts / 1000, tz=UTC).isoformat()
        elif ts is None:
            ts = ""

        entries.append(HistoryEntry(
            version=item.get("version", 0),
            timestamp=ts,
            operation=item.get("operation", ""),
            parameters=item.get("operationParameters") or {},
            description=item.get("userMetadata") or None,
            engine_info=item.get("engineInfo") or None,
        ))
    return entries


class DeltaReader:
    def can_read(self, uri: str, storage_options: dict | None = None) -> bool:
        try:
            deltalake.DeltaTable(uri, storage_options=storage_options)
            return True
        except Exception:
            return False

    def read(self, uri: str, name: str, sample_count: int = 0, storage_options: dict | None = None, history_limit: int | None = None) -> TableDoc:
        dt = deltalake.DeltaTable(uri, storage_options=storage_options)
        history = _parse_history(dt.history(limit=history_limit))

        lf = pl.scan_delta(uri, storage_options=storage_options)
        schema = lf.collect_schema()

        now = datetime.now(UTC)
        timestamp = now.isoformat()

        delta_schema = dt.schema()
        fields_by_name = {f.name: f for f in delta_schema.fields}
        metadata = dt.metadata()
        partition_columns = metadata.partition_columns
        partitioned_set = set(partition_columns)

        columns = []
        for pos, (col, dtype) in enumerate(schema.items(), start=1):
            data_type, precision, scale = _polars_type(dtype)
            delta_field = fields_by_name.get(col)
            description, tags = _column_metadata((delta_field.metadata if delta_field else None) or {})
            columns.append(Column(
                name=col,
                dataType=data_type,
                nullable=delta_field.nullable if delta_field else True,
                ordinalPosition=pos,
                precision=precision,
                scale=scale,
                partitioned=col in partitioned_set,
                description=description,
                tags=tags,
            ))

        row_count = lf.select(pl.len()).collect(engine="streaming").item()

        raw_stats = profile(lf, schema, now)
        column_profiles = []
        for col, s in raw_stats.items():
            column_profiles.append(ColumnProfile(
                name=col,
                timestamp=timestamp,
                valuesCount=s.get("valuesCount"),
                nullCount=s.get("nullCount"),
                mean=s.get("mean"),
                stddev=s.get("stddev"),
                min=s.get("min"),
                firstQuartile=s.get("firstQuartile"),
                median=s.get("median"),
                thirdQuartile=s.get("thirdQuartile"),
                max=s.get("max"),
                uniqueCount=s.get("uniqueCount"),
                top=s.get("top"),
                freq=s.get("freq"),
                distribution=s.get("distribution"),
            ))

        table_profile = TableProfile(
            timestamp=timestamp,
            rowCount=row_count,
            columnCount=len(columns),
            columnProfile=column_profiles,
        )

        sample_data: SampleData | None = None
        if sample_count > 0:
            col_names = [c.name for c in columns]
            rows = []
            for row in lf.limit(sample_count).collect(engine="streaming").to_dicts():
                clean = []
                for k in col_names:
                    v = row[k]
                    if isinstance(v, (str, int, float, bool, type(None))):
                        clean.append(v)
                    elif hasattr(v, "isoformat"):
                        clean.append(v.isoformat())
                    else:
                        clean.append(str(v))
                rows.append(clean)
            sample_data = SampleData(columns=col_names, rows=rows)

        parts = name.split("/")
        short_name = parts[-1]
        fqn = ".".join(parts)

        return TableDoc(
            name=short_name,
            fullyQualifiedName=fqn,
            uri=uri,
            updatedAt=timestamp,
            columns=columns,
            tableProfile=table_profile,
            description=metadata.description or None,
            partitionColumns=partition_columns,
            sampleData=sample_data,
            extension={"deltaHistory": history} if history else None,
            freshness=freshness(history, now),
            # Versions are numbered from 0 without gaps, so this counts every commit ever made,
            # including those whose log files have since been cleaned up or weren't read.
            commitCount=dt.version() + 1,
        )
