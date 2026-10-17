import argparse
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from datalake_doco.models import Catalog, CatalogEntry, TableDoc
from datalake_doco.readers.delta import DeltaReader
from datalake_doco.scanner import scan
from datalake_doco.writer import (
    copy_frontend,
    init_output_dir,
    write_catalog,
    write_table_doc,
)


def generate(
    uris: list[str],
    output: Path,
    sample_data_count: int,
    sample_data_exclude_tables: str,
    history_limit: int | None,
) -> None:
    generated_at = datetime.now(UTC).isoformat()

    excluded = {t.strip() for t in sample_data_exclude_tables.split(",") if t.strip()}

    endpoint_url = os.environ.get("AWS_ENDPOINT_URL_S3")
    storage_options: dict | None = {"AWS_ENDPOINT_URL": endpoint_url} if endpoint_url else None

    all_discovered: list[tuple[str, str]] = []
    for uri in uris:
        print(f"Scanning {uri} ...")
        discovered = scan(uri, endpoint_url=endpoint_url)
        print(f"  Found {len(discovered)} table(s)")
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

    print(f"\nDone. {len(table_docs)} table(s) documented → {output}")
    print(f"Serve with: python -m http.server 8000 --directory {output}")


def publish(output: Path) -> None:
    """Copy the frontend (HTML/CSS/JS) to the output directory without re-profiling tables."""
    copy_frontend(output)
    print(f"Frontend published → {output}")
    print(f"Serve with: python -m http.server 8000 --directory {output}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="datalake-doco",
        description="Generate static documentation for a datalake.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_parser = subparsers.add_parser("generate", help="Scan URIs, profile tables, write output.")
    generate_parser.add_argument("uris", nargs="+", help="One or more URIs to scan (S3 or local paths).")
    generate_parser.add_argument("--output", "-o", type=Path, default=Path("./datalake-docs"), help="Output directory.")
    generate_parser.add_argument("--sample-data-count", type=int, default=0, help="Number of sample rows to include per table.")
    generate_parser.add_argument("--sample-data-exclude-tables", default="", help="Comma-separated table names to exclude from sample data.")
    generate_parser.add_argument("--history-limit", type=int, default=None, help="Max number of history entries to include per table (default: unlimited).")
    generate_parser.set_defaults(func=lambda args: generate(
        args.uris, args.output, args.sample_data_count, args.sample_data_exclude_tables, args.history_limit,
    ))

    publish_parser = subparsers.add_parser("publish", help="Copy frontend assets without re-profiling tables.")
    publish_parser.add_argument("--output", "-o", type=Path, default=Path("./datalake-docs"), help="Output directory.")
    publish_parser.set_defaults(func=lambda args: publish(args.output))

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
