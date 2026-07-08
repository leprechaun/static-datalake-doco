import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import typer

from datalake_doco.models import Catalog, CatalogEntry
from datalake_doco.readers.delta import DeltaReader
from datalake_doco.scanner import scan
from datalake_doco.writer import copy_frontend, write_output

app = typer.Typer(help="Generate static documentation for a datalake.")


def _profile_table(
    table_uri: str,
    table_name: str,
    sample_count: int,
    storage_options: dict | None,
    history_limit: int | None,
) -> tuple:
    doc = DeltaReader().read(table_uri, table_name, sample_count=sample_count, storage_options=storage_options, history_limit=history_limit)
    return doc, table_name, table_uri


@app.command()
def generate(
    uris: list[str] = typer.Argument(..., help="One or more URIs to scan (S3 or local paths)."),
    output: Path = typer.Option(Path("./datalake-docs"), "--output", "-o", help="Output directory."),
    sample_data_count: int = typer.Option(0, "--sample-data-count", help="Number of sample rows to include per table."),
    sample_data_exclude_tables: str = typer.Option("", "--sample-data-exclude-tables", help="Comma-separated table names to exclude from sample data."),
    workers: int = typer.Option(8, "--workers", "-w", help="Number of parallel workers for profiling tables."),
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

    table_docs = []
    catalog_entries = []

    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                _profile_table,
                table_uri,
                table_name,
                0 if table_name.replace("/", ".") in excluded else sample_data_count,
                storage_options,
                history_limit,
            ): (table_uri, table_name)
            for table_uri, table_name in all_discovered
        }

        for future in as_completed(futures):
            table_uri, table_name = futures[future]
            try:
                doc, _, _ = future.result()
            except Exception as exc:
                typer.echo(f"  [error] {table_name}: {exc}", err=True)
                continue

            if doc is None:
                typer.echo(f"  [skip] No reader for {table_uri}", err=True)
                continue

            typer.echo(f"  Profiled {doc.fullyQualifiedName}")
            table_docs.append(doc)

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

    table_docs.sort(key=lambda d: d.fullyQualifiedName)
    catalog_entries.sort(key=lambda e: e.fullyQualifiedName)

    catalog = Catalog(
        generatedAt=generated_at,
        sources=uris,
        tables=catalog_entries,
    )

    write_output(catalog, table_docs, output)

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
