# datalake-doco

[![Maintainability](https://qlty.sh/gh/leprechaun/projects/static-datalake-doco/maintainability.svg)](https://qlty.sh/gh/leprechaun/projects/static-datalake-doco)
[![Code Coverage](https://qlty.sh/gh/leprechaun/projects/static-datalake-doco/coverage.svg)](https://qlty.sh/gh/leprechaun/projects/static-datalake-doco)

## Purpose

<img width="300" alt="Image" src="https://github.com/user-attachments/assets/553ee789-b0fe-45be-925b-7e920024cba3" />
<img width="300" alt="Image" src="https://github.com/user-attachments/assets/2c53cfb7-a966-45b2-8b7b-69ef3cb4d8dc" />
<img width="300" alt="Image" src="https://github.com/user-attachments/assets/11826c47-98db-4b6a-b3ac-3a97e4149f9a" />
<img width="300" alt="Image" src="https://github.com/user-attachments/assets/fcd5b2df-2e60-46c8-b8fb-6e2e9c22f07e" />

```
a.k.a. "Poor Man's Data Catalogue"
```

This tool will generate a data catalogue after scanning an S3 bucket. The catalogue is a set of OpenMetadata-looking JSON files, and a catalogue. There's also a static HTML page that can be used to view the catalogue as human being.

Why? Because it's easy, quick, and does not require spinning up any sort of machinery.

Each table's documentation includes the schema, row count, version history, statistics, and a time distribution for each date/timestamp column. Sample data is off by default; turn it on with `--sample-data-count`, and leave out individual tables with `--sample-data-exclude-tables` in case there are concerns with data sensitivity.

## Usage

`datalake-doco generate` scans one or more filesystem or S3 roots for Delta Lake tables, profiles each table, and writes a static JSON catalog plus per-table JSON documents to an output directory. The output is self-contained and can be served by any static HTTP server.

---

## Pipeline

```
URI(s)
  └─ scanner.scan()             → list[(table_uri, table_name)]
  └─ writer.init_output_dir() + copy_frontend()
  └─ per table:
       └─ DeltaReader.read()    → TableDoc
            ├─ profiler.profile()     → column statistics + time distributions
            ├─ dt.history()           → Delta transaction log
            └─ freshness.freshness()  → last write vs typical write interval
       └─ writer.write_table_doc() + write_catalog() → tables/**/*.json, catalog.json
  └─ writer.write_llm_docs()    → llms.txt + tables/**/*.md
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
| `--history-limit` | `int` | `100` | Max history entries read per table (`0` = all). Each entry is a separate commit file fetched from storage, so busy tables with thousands of commits make many requests |
| `--base-url` | `str` | `None` | Public URL of the output directory. Makes links in `llms.txt` and the table Markdown absolute (`None` = relative links) |

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

### Description

`description` ← the Delta table's metadata description (`DeltaTable.metadata().description`). `None` if absent or empty.

### Column schema

Each column in the polars schema produces one `Column`:

- `name` — column name
- `dataType` — mapped from polars dtype (see type mapping below)
- `nullable` — from the Delta schema field, **not** inferred from data
- `ordinalPosition` — 1-indexed position in the schema
- `precision`, `scale` — set only for `DECIMAL`; `None` otherwise
- `partitioned` — whether the column is one of the Delta table's partition columns (also listed in `TableDoc.partitionColumns`)

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

- `rowCount` — total rows in the table (a streaming `pl.len()` over the scan)
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
- Limited to the `history_limit` most-recent entries when set (the CLI defaults to 100, `config.DEFAULT_HISTORY_LIMIT`); all entries otherwise. Freshness is computed from these entries, so a limit below about 100 shortens the window for the typical write interval.
- `timestamp` is converted from epoch-milliseconds to ISO 8601 UTC string; stored as `""` if absent.
- `parameters` ← `operationParameters` (empty dict if absent).
- `description` ← `userMetadata` (`None` if absent/empty).
- `engine_info` ← `engineInfo` (`None` if absent/empty).
- If the history list is empty, `extension` is `None`.
- `commitCount` (top level, not under `extension`) is the latest version + 1: every commit ever made, however many history entries were read and even after old log files are cleaned up.

### Freshness

`freshness` (also copied to the table's `catalog.json` entry) comes from the data-changing commits in the history (`config.DATA_OPERATIONS`: `WRITE`, `MERGE`, `DELETE`, `UPDATE`):

- `lastWrite`, `secondsSinceLastWrite` — the newest data commit, and its age at profiling time
- `typicalIntervalSeconds` — median of the last `config.FRESHNESS_GAPS` (49) gaps between data commits; `null` with only one commit. Gaps under `config.BURST_GAP_SECONDS` (60) are left out, so a burst of commits such as a backfill counts as one write. A table with fewer than `config.MIN_INTERVAL_GAPS` (3) longer gaps really does write that often, so all its gaps count
- `burstGapSeconds` — the burst threshold applied, or `null` when all gaps counted
- `ratio` — `secondsSinceLastWrite / typicalIntervalSeconds`
- `intervalGaps`, `dataCommits` — gaps used for the interval, and data commits in the history
- `null` when the history has no data commits.

---

## Profiler

**`profiler.profile(lf: pl.LazyFrame, schema, now=None) → dict[str, dict]`**

Returns a dict keyed by column name. Field names are OpenMetadata-aligned. Every column's statistics are computed in a single streaming pass over `lf`; `now` (default: the current UTC time) is the profiling time used to mark partial periods in time distributions.

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

### Other columns (string, boolean, etc.)

| Field | Description |
|---|---|
| `valuesCount` | Non-null row count |
| `nullCount` | Null row count |
| `uniqueCount` | Number of distinct values (including null) |
| `top` | Most frequent non-null value as a string, or `null` if all values are null |
| `freq` | Occurrence count of `top`, or `null` if all values are null |

`mean`, `stddev`, `min`, `firstQuartile`, `median`, `thirdQuartile`, and `max` are **absent**.

### Temporal columns (date, timestamp, duration, time)

`valuesCount`, `nullCount`, and `min`/`max` as ISO strings. Date and timestamp columns also get a `distribution`, built from per-hour (timestamp) or per-day (date) row counts gathered in the same single pass as the other statistics:

| Field | Description |
|---|---|
| `grain` | `monthly` (every value is midnight on the 1st), `daily` (every value is midnight) or `sub-daily` |
| `bucketing` | Time zone tz-aware timestamps were converted to before bucketing (`config.BUCKET_TIMEZONE`, default `UTC`), or `naive`/`date` for values bucketed as stored |
| `year`, `month`, `day` | Row counts per period that has rows |
| `weekday`, `hour` | Row counts per weekday and hour of day, every slot listed; `hour` only for sub-daily timestamps |
| `daysWithData`, `missingDays`, `largestGap` | Days with rows, days without rows between the first and last, and the longest run of those |
| `gaps` | Runs of missing days (or months, for monthly columns), largest first |
| `rowsPerDay` | min, p5, median, p95 and max rows per day with data, excluding the partial day; not for monthly columns |
| `partialDay`, `partialMonth` | The day and month still in progress at profiling time |
| `sameAs` | Set when the column's per-day counts repeat another column's: `derived` for a date matching a timestamp, `identical` otherwise |

### Float safety

Any stat that is `NaN` or `±Inf` is replaced with `null`. Values are rounded to 6 decimal places.

---

## Writer

`generate` writes the output incrementally, so a long run leaves a usable catalogue behind as it goes:

1. `init_output_dir` creates `output_dir` if it does not exist, and deletes and recreates `output_dir/tables/`.
2. `copy_frontend` copies the assets from the package's `frontend/` directory into `output_dir`, and an empty `catalog.json` is written.
3. As each table finishes, `write_table_doc` writes `output_dir/tables/{fullyQualifiedName.replace(".", "/")}.json` (creating intermediate directories as needed) and `catalog.json` is rewritten with the tables so far.
4. `write_llm_docs` writes `llms.txt` and one `tables/{path}.md` per table once every table is profiled.

`write_output(catalog, table_docs, output_dir, base_url=None)` does all of that in one call, for already-profiled tables.

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
      "columnCount": 12,
      "description": "Raw clickstream events",
      "freshness": {"lastWrite": "<ISO 8601 UTC>", "secondsSinceLastWrite": 900, "typicalIntervalSeconds": 3600, "intervalGaps": 49, "burstGapSeconds": 60, "dataCommits": 812, "ratio": 0.25}
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
  "description": "Raw clickstream events",
  "columns": [
    {
      "name": "id",
      "dataType": "BIGINT",
      "nullable": true,
      "ordinalPosition": 1,
      "precision": null,
      "scale": null,
      "partitioned": false
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
        "freq": null,
        "distribution": null
      },
      {
        "name": "ts",
        "timestamp": "<ISO 8601 UTC>",
        "valuesCount": 1000000.0,
        "nullCount": 0.0,
        "min": "2026-09-01T02:04:50+00:00",
        "max": "2026-11-06T13:24:03+00:00",
        "distribution": {
          "grain": "sub-daily",
          "bucketing": "UTC",
          "partialDay": "2026-11-06",
          "partialMonth": "2026-11",
          "daysWithData": 66,
          "missingDays": 1,
          "largestGap": {"start": "2026-10-04", "end": "2026-10-04", "days": 1},
          "gaps": [{"start": "2026-10-04", "end": "2026-10-04", "count": 1}],
          "rowsPerDay": {"min": 9800, "p5": 14100.5, "median": 15200, "p95": 16050.25, "max": 17000},
          "year": {"2026": 1000000},
          "month": {"2026-09": 450000, "2026-10": 460000, "2026-11": 90000},
          "day": {"2026-09-01": 9800, "...": 0},
          "weekday": {"Mon": 142000, "Tue": 143000, "Wed": 144000, "Thu": 143500, "Fri": 142500, "Sat": 142000, "Sun": 143000},
          "hour": {"00": 41000, "...": 0, "23": 41500}
        }
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
  },
  "partitionColumns": [],
  "commitCount": 84142,
  "freshness": {"lastWrite": "<ISO 8601 UTC>", "secondsSinceLastWrite": 900, "typicalIntervalSeconds": 3600, "intervalGaps": 49, "burstGapSeconds": 60, "dataCommits": 812, "ratio": 0.25}
}
```

`description` is `null` when the Delta table has no description. `sampleData` is `null` when `--sample-data-count` is `0` or the table is excluded. `extension` is `null` when the Delta table has no history. `freshness` is `null` when the history has no data-changing commits. `"..."` in the example above stands for the omitted per-day and per-hour entries.

---

### LLM docs (`llms.txt` + `tables/{path}.md`)

Written at the end of `generate`, next to the JSON, so the same static server exposes them. Point an agent with a fetch tool at `<server>/llms.txt` and it can follow the links to each table.

- `llms.txt` — one section per group (the fully qualified name minus the table name, e.g. `gadgetbridge.gold`), one linked line per table with its description, row and column counts, and the age of its last write compared to its typical write interval.
- `tables/{path}.md` — description, row/column counts, partition columns, location, total Delta commits, last write and typical write interval, schema, statistics (nulls, distinct, min, mean, max, most common), a time distribution per date/timestamp column (grain, bucketing time zone, rows per day, gaps, a year × month grid with the partial month marked, rows by weekday and hour; a column with the same per-day counts as another is collapsed to one line), sample rows, the last 5 history entries, and links to the other tables in the same group, to the table's JSON and back to `llms.txt`.

Links are relative to the file they appear in, unless `--base-url` is given. Use `--base-url` when the files will be pasted into a chat rather than fetched, so the links still resolve. If the docs are published where a cloud-hosted LLM can reach them, consider generating without `--sample-data-count`.

---

## Missing Features

- Non-Delta table formats (Parquet, Iceberg, Hudi, etc.)

## Out of scope

- Tables with zero columns
- Incremental / append-only catalog updates
- S3 credential configuration: only the endpoint (`AWS_ENDPOINT_URL_S3`) is passed explicitly; credentials come from the standard `AWS_*` environment variables, read by `fsspec`/`s3fs` when scanning and by `deltalake`/Polars when reading tables
- Column ordering guarantees beyond schema order
