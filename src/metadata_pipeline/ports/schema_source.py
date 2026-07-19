"""Provider-neutral schema source contract and data transfer objects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class SchemaSourceError(ValueError):
    """Raised when a schema source cannot produce a valid catalog."""


@dataclass(frozen=True)
class ColumnSchema:
    """Technical description of one database column."""

    name: str
    data_type: str
    nullable: bool
    comment: str


@dataclass(frozen=True)
class TableSchema:
    """Technical description of one database table."""

    name: str
    table_type: str
    comment: str
    columns: tuple[ColumnSchema, ...]


@dataclass(frozen=True)
class RelationSchema:
    """Logical or physical relation between database tables."""

    table: str
    columns: tuple[str, ...]
    parent_table: str
    parent_columns: tuple[str, ...]
    definition: str
    virtual: bool


@dataclass(frozen=True)
class DatabaseSchema:
    """Provider-neutral database schema consumed by later application use cases."""

    name: str
    description: str
    tables: tuple[TableSchema, ...]
    relations: tuple[RelationSchema, ...]


class SchemaSource(Protocol):
    """Load technical schema metadata from an external representation."""

    def load(self) -> DatabaseSchema:
        """Return a validated provider-neutral schema catalog."""
