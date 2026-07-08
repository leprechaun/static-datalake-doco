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
class Column:
    name: str
    dataType: str
    nullable: bool
    ordinalPosition: int
    precision: int | None = None
    scale: int | None = None


@dataclass
class ColumnProfile:
    name: str
    timestamp: str
    valuesCount: float | None = None
    nullCount: float | None = None
    mean: float | None = None
    stddev: float | None = None
    min: float | None = None
    firstQuartile: float | None = None
    median: float | None = None
    thirdQuartile: float | None = None
    max: float | None = None
    uniqueCount: int | None = None
    top: str | None = None
    freq: int | None = None


@dataclass
class TableProfile:
    timestamp: str
    rowCount: int
    columnCount: int
    columnProfile: list[ColumnProfile]


@dataclass
class SampleData:
    columns: list[str]
    rows: list[list[Any]]


@dataclass
class TableDoc:
    name: str
    fullyQualifiedName: str
    uri: str
    updatedAt: str
    columns: list[Column]
    tableProfile: TableProfile
    sampleData: SampleData | None = None
    extension: dict[str, Any] | None = None


@dataclass
class CatalogEntry:
    fullyQualifiedName: str
    name: str
    uri: str
    docPath: str
    updatedAt: str
    rowCount: int
    columnCount: int


@dataclass
class Catalog:
    generatedAt: str
    sources: list[str]
    tables: list[CatalogEntry]
