import dataclasses
import json
import shutil
from pathlib import Path

from datalake_doco.models import Catalog, TableDoc


def _to_dict(obj):
    if dataclasses.is_dataclass(obj):
        return {k: _to_dict(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, list):
        return [_to_dict(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    return obj


def write_output(catalog: Catalog, table_docs: list[TableDoc], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)

    catalog_path = output_dir / "catalog.json"
    catalog_path.write_text(json.dumps(_to_dict(catalog), indent=2), encoding="utf-8")

    for doc in table_docs:
        doc_file = tables_dir / f"{doc.name}.json"
        doc_file.parent.mkdir(parents=True, exist_ok=True)
        doc_file.write_text(json.dumps(_to_dict(doc), indent=2), encoding="utf-8")

    copy_frontend(output_dir)


def copy_frontend(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    frontend_src = Path(__file__).parent / "frontend"
    for asset in frontend_src.iterdir():
        shutil.copy2(asset, output_dir / asset.name)
