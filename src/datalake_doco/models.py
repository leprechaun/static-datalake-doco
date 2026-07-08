from dataclasses import dataclass, field
from typing import Any


@dataclass
class HistoryEntry:
    version: int
    timestamp: str
    operation: str
    parameters: dict[str, Any]
    description: str | None
    engine_info: str | None


@dataclass
class ColumnSchema:
    name: str
    type: str
    nullable: bool


@dataclass
class ColumnStats:
    count: float | None = None
    mean: float | None = None
    std: float | None = None
    min: float | None = None
    p25: float | None = None
    p50: float | None = None
    p75: float | None = None
    max: float | None = None
    unique: int | None = None
    top: str | None = None
    freq: int | None = None


@dataclass
class TableDoc:
    name: str
    uri: str
    generated_at: str
    format: str
    row_count: int
    schema: list[ColumnSchema]
    statistics: dict[str, ColumnStats]
    sample_data: list[dict[str, Any]] = field(default_factory=list)
    history: list[HistoryEntry] = field(default_factory=list)


@dataclass
class CatalogEntry:
    name: str
    uri: str
    doc_path: str
    generated_at: str
    row_count: int
    column_count: int


@dataclass
class Catalog:
    generated_at: str
    sources: list[str]
    tables: list[CatalogEntry]
