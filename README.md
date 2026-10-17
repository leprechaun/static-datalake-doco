# datalake-doco — Backend Specification

[![Maintainability](https://qlty.sh/gh/leprechaun/projects/static-datalake-doco/maintainability.svg)](https://qlty.sh/gh/leprechaun/projects/static-datalake-doco)
[![Code Coverage](https://qlty.sh/gh/leprechaun/projects/static-datalake-doco/coverage.svg)](https://qlty.sh/gh/leprechaun/projects/static-datalake-doco)

## Purpose

`datalake-doco generate` scans one or more filesystem or S3 roots for Delta Lake tables, profiles each table, and writes a static JSON catalog plus per-table JSON documents to an output directory. The output is self-contained and can be served by any static HTTP server.

---

## Pipeline

```
URI(s)
  └─ scanner.scan()          → list[(table_uri, table_name)]
       └─ DeltaReader.read() → TableDoc
            ├─ profiler.profile() → column statistics
            └─ dt.history()      → Delta transaction log
  └─ writer.write_output()   → catalog.json + tables/**/*.json + frontend assets
```

---

## CLI

### `generate`

Scans URIs, profiles all discovered Delta tables, and writes the full output.

| Argument / Option | Type | Default | Description |
|---|---|---|---|
| `uris` | `list[str]` (positional, 1+) | required | Roots to scan (local path or `s3://...`) |
| `--output` / `-o` | `Path` | `./datalake-docs` | Output directory |
| `--sample-data-count` | `int` | `0` | Sample rows per table (`0` = no sample data) |
| `--sample-data-exclude-tables` | `str` | `""` | Comma-separated `fullyQualifiedName`s to exclude from sample data |
| `--history-limit` | `int` | `None` | Max history entries per table (`None` = all) |

**Environment:**
- `AWS_ENDPOINT_URL_S3` — if set, used as the S3 endpoint for both scanning and reading. Enables MinIO and other S3-compatible stores.

**Behaviour:**
- Tables from all URIs are merged into one catalog.
- Tables that fail to profile are skipped, with an `[error]` line printed in place of `done`; they do not appear in the catalog.
- Tables are profiled sequentially; each progress line is printed as soon as profiling starts and completed in place once it finishes.
- `--sample-data-exclude-tables` is matched against `fullyQualifiedName` (dots, not slashes). Excluded tables are still profiled and appear in the catalog — only sample rows are omitted.
- The `tables/` subdirectory in the output is deleted and recreated on each run.

### `publish`

Copies only the frontend assets (`index.html`, `app.js`, `style.css`) to `--output`. Does not re-profile tables. Use this to update the UI without re-scanning the datalake.

---

## Scanner

**`scanner.scan(uri, endpoint_url=None) → list[tuple[str, str]]`**

Returns `(table_uri, table_name)` pairs for every Delta table found under `uri`.

**Detection:** A directory is a Delta table if and only if it contains a child named `_delta_log`. Recursion stops at that point — subdirectories of a Delta table are not visited.

**`table_uri`:** Absolute path or full URI of the table root (no trailing slash).

**`table_name`:** Path of `table_uri` relative to the scan root, with the root prefix and leading slash stripped. If the table is the root itself, falls back to the final path segment.

Examples (root = `/data`):

| Table path | `table_name` |
|---|---|
| `/data/events` | `events` |
| `/data/bronze/events` | `bronze/events` |
| `/data/mydb/bronze/events` | `mydb/bronze/events` |

Trailing slashes in `uri` are stripped before processing.

---

## DeltaReader

**`DeltaReader().read(uri, name, sample_count=0, storage_options=None, history_limit=None) → TableDoc`**

### Name → identity fields

`name` uses `/` as the segment separator (matches scanner output).

| `name` input | `TableDoc.name` | `TableDoc.fullyQualifiedName` |
|---|---|---|
| `events` | `events` | `events` |
| `bronze/events` | `events` | `bronze.events` |
| `mydb/bronze/events` | `events` | `mydb.bronze.events` |

Rule: `name` = last `/`-segment; `fullyQualifiedName` = `name` with `/` replaced by `.`.

### Column schema

Each column in the polars schema produces one `Column`:

- `name` — column name
- `dataType` — mapped from polars dtype (see type mapping below)
- `nullable` — from the Delta schema field, **not** inferred from data
- `ordinalPosition` — 1-indexed position in the schema
- `precision`, `scale` — set only for `DECIMAL`; `None` otherwise

**Type mapping:**

| Polars dtype | `dataType` |
|---|---|
| `Int8`, `UInt8` | `TINYINT` |
| `Int16`, `UInt16` | `SMALLINT` |
| `Int32`, `UInt32` | `INT` |
| `Int64`, `UInt64` | `BIGINT` |
| `Float32` | `FLOAT` |
| `Float64` | `DOUBLE` |
| `Boolean` | `BOOLEAN` |
| `String`, `Utf8` | `STRING` |
| `Date` | `DATE` |
| `Binary` | `BINARY` |
| `Datetime(any)` | `TIMESTAMP` |
| `Decimal(p, s)` | `DECIMAL` (precision=p, scale=s) |
| `List`, `Array` | `ARRAY` |
| `Struct` | `STRUCT` |
| anything else | `str(dtype).upper()` |

### Table profile

- `rowCount` — total rows in the table (`df.height`)
- `columnCount` — number of columns in the schema
- `timestamp` — ISO 8601 UTC timestamp at the moment of profiling
- `columnProfile` — one `ColumnProfile` per column

### Sample data

Produced only when `sample_count > 0`.

- `columns` — column names in schema order
- `rows` — up to `sample_count` rows from the head of the table
- Cell values are coerced to JSON-safe types: `str`, `int`, `float`, `bool`, or `None`. Date/datetime values are serialised via `.isoformat()`; anything else via `str()`.

### Delta history

- Stored under `extension["deltaHistory"]` as a list of `HistoryEntry`.
- Limited to the `history_limit` most-recent entries when set; all entries otherwise.
- `timestamp` is converted from epoch-milliseconds to ISO 8601 UTC string; stored as `""` if absent.
- `parameters` ← `operationParameters` (empty dict if absent).
- `description` ← `userMetadata` (`None` if absent/empty).
- `engine_info` ← `engineInfo` (`None` if absent/empty).
- If the history list is empty, `extension` is `None`.

---

## Profiler

**`profiler.profile(df: pl.DataFrame) → dict[str, dict]`**

Returns a dict keyed by column name. Field names are OpenMetadata-aligned.

### Numeric columns

| Field | Description |
|---|---|
| `valuesCount` | Non-null row count |
| `nullCount` | Null row count |
| `mean` | Arithmetic mean |
| `stddev` | Standard deviation |
| `min` | Minimum value |
| `firstQuartile` | 25th percentile |
| `median` | 50th percentile |
| `thirdQuartile` | 75th percentile |
| `max` | Maximum value |

`uniqueCount`, `top`, and `freq` are **absent** (not present as `None`).

### Non-numeric columns (string, date, boolean, etc.)

| Field | Description |
|---|---|
| `valuesCount` | Non-null row count |
| `nullCount` | Null row count |
| `uniqueCount` | Number of distinct values (including null) |
| `top` | Most frequent non-null value as a string, or `null` if all values are null |
| `freq` | Occurrence count of `top`, or `null` if all values are null |

`mean`, `stddev`, `min`, `firstQuartile`, `median`, `thirdQuartile`, and `max` are **absent**.

### Float safety

Any stat that is `NaN` or `±Inf` is replaced with `null`. Values are rounded to 6 decimal places.

---

## Writer

**`writer.write_output(catalog, table_docs, output_dir) → None`**

1. Creates `output_dir` if it does not exist.
2. Deletes and recreates `output_dir/tables/`.
3. Writes `output_dir/catalog.json`.
4. For each `TableDoc`, writes `output_dir/tables/{fullyQualifiedName.replace(".", "/")}.json`, creating intermediate directories as needed.
5. Copies frontend assets from the package's `frontend/` directory into `output_dir`.

**JSON serialisation:** Dataclasses are recursively converted to plain dicts. `float` values that are `NaN` or `±Inf` are replaced with `null`. Output is UTF-8, indented with 2 spaces.

---

## Output schema

### `catalog.json`

```json
{
  "generatedAt": "<ISO 8601 UTC>",
  "sources": ["<uri>"],
  "tables": [
    {
      "fullyQualifiedName": "mydb.bronze.events",
      "name": "events",
      "uri": "<absolute table URI>",
      "docPath": "tables/mydb/bronze/events.json",
      "updatedAt": "<ISO 8601 UTC>",
      "rowCount": 1000000,
      "columnCount": 12
    }
  ]
}
```

### `tables/{path}.json`

```json
{
  "name": "events",
  "fullyQualifiedName": "mydb.bronze.events",
  "uri": "<absolute table URI>",
  "updatedAt": "<ISO 8601 UTC>",
  "columns": [
    {
      "name": "id",
      "dataType": "BIGINT",
      "nullable": true,
      "ordinalPosition": 1,
      "precision": null,
      "scale": null
    }
  ],
  "tableProfile": {
    "timestamp": "<ISO 8601 UTC>",
    "rowCount": 1000000,
    "columnCount": 12,
    "columnProfile": [
      {
        "name": "id",
        "timestamp": "<ISO 8601 UTC>",
        "valuesCount": 1000000.0,
        "nullCount": 0.0,
        "mean": 500000.5,
        "stddev": 288675.1,
        "min": 1.0,
        "firstQuartile": 250000.75,
        "median": 500000.5,
        "thirdQuartile": 750000.25,
        "max": 1000000.0,
        "uniqueCount": null,
        "top": null,
        "freq": null
      }
    ]
  },
  "sampleData": {
    "columns": ["id", "name"],
    "rows": [[1, "alice"], [2, "bob"]]
  },
  "extension": {
    "deltaHistory": [
      {
        "version": 5,
        "timestamp": "<ISO 8601 UTC>",
        "operation": "WRITE",
        "parameters": {"mode": "Append"},
        "description": null,
        "engine_info": "Delta-Rust/0.19.0"
      }
    ]
  }
}
```

`sampleData` is `null` when `--sample-data-count` is `0` or the table is excluded. `extension` is `null` when the Delta table has no history.

---

## Out of scope

- Non-Delta table formats (Parquet, Iceberg, Hudi, etc.)
- Tables with zero columns
- Incremental / append-only catalog updates
- S3 credential configuration (delegated to `fsspec`/`s3fs` conventions)
- Column ordering guarantees beyond schema order
