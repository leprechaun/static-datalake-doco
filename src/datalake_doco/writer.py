import dataclasses
import json
import math
import shutil
from pathlib import Path

from datalake_doco.markdown import (
    group_of,
    render_llms_txt,
    render_table_md,
    table_md_path,
)
from datalake_doco.models import Catalog, TableDoc


def _to_dict(obj):
    if dataclasses.is_dataclass(obj):
        return {k: _to_dict(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, list):
        return [_to_dict(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


def init_output_dir(output_dir: Path) -> None:
    """Create output_dir and reset its tables/ subdirectory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    tables_dir = output_dir / "tables"
    if tables_dir.exists():
        shutil.rmtree(tables_dir)
    tables_dir.mkdir()


def write_catalog(catalog: Catalog, output_dir: Path) -> None:
    catalog_path = output_dir / "catalog.json"
    catalog_path.write_text(json.dumps(_to_dict(catalog), indent=2), encoding="utf-8")


def write_table_doc(output_dir: Path, doc: TableDoc) -> None:
    rel_path = doc.fullyQualifiedName.replace(".", "/")
    doc_file = output_dir / "tables" / f"{rel_path}.json"
    doc_file.parent.mkdir(parents=True, exist_ok=True)
    doc_file.write_text(json.dumps(_to_dict(doc), indent=2), encoding="utf-8")


def write_llm_docs(catalog: Catalog, table_docs: list[TableDoc], output_dir: Path, base_url: str | None = None) -> None:
    """Write llms.txt and a Markdown page per table, linking each table to the others in its group."""
    (output_dir / "llms.txt").write_text(render_llms_txt(catalog, base_url), encoding="utf-8")
    for doc in table_docs:
        group = group_of(doc.fullyQualifiedName)
        related = [
            e for e in catalog.tables
            if e.fullyQualifiedName != doc.fullyQualifiedName and group_of(e.fullyQualifiedName) == group
        ]
        md_file = output_dir / table_md_path(doc.fullyQualifiedName)
        md_file.parent.mkdir(parents=True, exist_ok=True)
        md_file.write_text(render_table_md(doc, related, base_url), encoding="utf-8")


def write_output(catalog: Catalog, table_docs: list[TableDoc], output_dir: Path, base_url: str | None = None) -> None:
    init_output_dir(output_dir)
    write_catalog(catalog, output_dir)
    for doc in table_docs:
        write_table_doc(output_dir, doc)
    write_llm_docs(catalog, table_docs, output_dir, base_url)
    copy_frontend(output_dir)


def copy_frontend(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    frontend_src = Path(__file__).parent / "frontend"
    for asset in frontend_src.iterdir():
        shutil.copy2(asset, output_dir / asset.name)
