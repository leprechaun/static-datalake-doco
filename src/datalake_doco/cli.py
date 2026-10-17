import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import typer

from datalake_doco.models import Catalog, CatalogEntry, TableDoc
from datalake_doco.readers.delta import DeltaReader
from datalake_doco.scanner import scan
from datalake_doco.writer import copy_frontend, init_output_dir, write_catalog, write_table_doc

app = typer.Typer(help="Generate static documentation for a datalake.")


@app.command()
def generate(
    uris: list[str] = typer.Argument(..., help="One or more URIs to scan (S3 or local paths)."),
    output: Path = typer.Option(Path("./datalake-docs"), "--output", "-o", help="Output directory."),
    sample_data_count: int = typer.Option(0, "--sample-data-count", help="Number of sample rows to include per table."),
    sample_data_exclude_tables: str = typer.Option("", "--sample-data-exclude-tables", help="Comma-separated table names to exclude from sample data."),
    history_limit: int = typer.Option(None, "--history-limit", help="Max number of history entries to include per table (default: unlimited)."),
) -> None:
    generated_at = datetime.now(timezone.utc).isoformat()

    excluded = {t.strip() for t in sample_data_exclude_tables.split(",") if t.strip()}

    endpoint_url = os.environ.get("AWS_ENDPOINT_URL_S3")
    storage_options: dict | None = {"AWS_ENDPOINT_URL": endpoint_url} if endpoint_url else None

    all_discovered: list[tuple[str, str]] = []
    for uri in uris:
        typer.echo(f"Scanning {uri} ...")
        discovered = scan(uri, endpoint_url=endpoint_url)
        typer.echo(f"  Found {len(discovered)} table(s)")
        all_discovered.extend(discovered)

    total = len(all_discovered)
    init_output_dir(output)
    copy_frontend(output)
    write_catalog(Catalog(generatedAt=generated_at, sources=uris, tables=[]), output)

    table_docs = []
    catalog_entries = []

    def record(table_uri: str, doc: TableDoc) -> None:
        table_docs.append(doc)
        write_table_doc(output, doc)

        doc_path = f"tables/{doc.fullyQualifiedName.replace('.', '/')}.json"
        catalog_entries.append(
            CatalogEntry(
                fullyQualifiedName=doc.fullyQualifiedName,
                name=doc.name,
                uri=table_uri,
                docPath=doc_path,
                updatedAt=doc.updatedAt,
                rowCount=doc.tableProfile.rowCount,
                columnCount=doc.tableProfile.columnCount,
            )
        )

        catalog = Catalog(
            generatedAt=generated_at,
            sources=uris,
            tables=sorted(catalog_entries, key=lambda e: e.fullyQualifiedName),
        )
        write_catalog(catalog, output)

    for idx, (table_uri, table_name) in enumerate(all_discovered, start=1):
        fqn = table_name.replace("/", ".")
        sample_count = 0 if fqn in excluded else sample_data_count

        sys.stdout.write(f"  [{idx}/{total}] {fqn} ... ")
        sys.stdout.flush()
        start = time.monotonic()

        try:
            doc = DeltaReader().read(table_uri, table_name, sample_count=sample_count, storage_options=storage_options, history_limit=history_limit)
        except Exception as exc:
            elapsed = time.monotonic() - start
            sys.stdout.write(f"[error] ({elapsed:.1f}s): {exc}\n")
            sys.stdout.flush()
            continue

        elapsed = time.monotonic() - start
        sys.stdout.write(f"done ({elapsed:.1f}s)\n")
        sys.stdout.flush()
        record(table_uri, doc)

    typer.echo(f"\nDone. {len(table_docs)} table(s) documented → {output}")
    typer.echo(f"Serve with: python -m http.server 8000 --directory {output}")


@app.command()
def publish(
    output: Path = typer.Option(Path("./datalake-docs"), "--output", "-o", help="Output directory."),
) -> None:
    """Copy the frontend (HTML/CSS/JS) to the output directory without re-profiling tables."""
    copy_frontend(output)
    typer.echo(f"Frontend published → {output}")
    typer.echo(f"Serve with: python -m http.server 8000 --directory {output}")
