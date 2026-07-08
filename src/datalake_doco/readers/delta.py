from datetime import datetime, timezone

import deltalake
import polars as pl

from datalake_doco.models import ColumnSchema, HistoryEntry, TableDoc
from datalake_doco.profiler import profile


def _polars_type_name(dtype: pl.DataType) -> str:
    mapping = {
        pl.Int8: "tinyint",
        pl.Int16: "smallint",
        pl.Int32: "int",
        pl.Int64: "bigint",
        pl.UInt8: "tinyint",
        pl.UInt16: "smallint",
        pl.UInt32: "int",
        pl.UInt64: "bigint",
        pl.Float32: "float",
        pl.Float64: "double",
        pl.Boolean: "boolean",
        pl.String: "string",
        pl.Utf8: "string",
        pl.Date: "date",
        pl.Binary: "binary",
    }
    for cls, name in mapping.items():
        if isinstance(dtype, cls):
            return name
    if isinstance(dtype, pl.Datetime):
        return "timestamp"
    if isinstance(dtype, pl.Decimal):
        return f"decimal({dtype.precision},{dtype.scale})"
    if isinstance(dtype, (pl.List, pl.Array)):
        return "array"
    if isinstance(dtype, pl.Struct):
        return "struct"
    return str(dtype).lower()


def _parse_history(raw: list[dict]) -> list[HistoryEntry]:
    entries = []
    for item in raw:
        ts = item.get("timestamp")
        if isinstance(ts, (int, float)):
            ts = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()
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

    def read(self, uri: str, name: str, sample_count: int = 0, storage_options: dict | None = None) -> TableDoc:
        dt = deltalake.DeltaTable(uri, storage_options=storage_options)
        history = _parse_history(dt.history())

        df = pl.read_delta(uri, storage_options=storage_options)

        schema = [
            ColumnSchema(
                name=col,
                type=_polars_type_name(dtype),
                nullable=True,
            )
            for col, dtype in df.schema.items()
        ]

        stats = profile(df)

        sample_data: list[dict] = []
        if sample_count > 0:
            for row in df.head(sample_count).to_dicts():
                clean = {}
                for k, v in row.items():
                    if isinstance(v, (str, int, float, bool, type(None))):
                        clean[k] = v
                    elif hasattr(v, "isoformat"):
                        clean[k] = v.isoformat()
                    else:
                        clean[k] = str(v)
                sample_data.append(clean)

        return TableDoc(
            name=name,
            uri=uri,
            generated_at=datetime.now(timezone.utc).isoformat(),
            format="delta",
            row_count=df.height,
            schema=schema,
            statistics=stats,
            sample_data=sample_data,
            history=history,
        )
