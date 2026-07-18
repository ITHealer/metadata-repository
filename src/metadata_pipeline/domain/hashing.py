"""Deterministic hashes for technical schema review boundaries."""

from __future__ import annotations

import hashlib
import json

from metadata_pipeline.ports.schema_source import DatabaseSchema, TableSchema


def table_schema_hash(schema: DatabaseSchema, table: TableSchema) -> str:
    """Return a stable SHA-256 hash for one table and its declared relations."""
    columns = [
        {
            "comment": column.comment,
            "data_type": column.data_type,
            "name": column.name,
            "nullable": column.nullable,
        }
        for column in sorted(table.columns, key=lambda item: item.name)
    ]
    related = (
        relation
        for relation in schema.relations
        if relation.table == table.name or relation.parent_table == table.name
    )
    relations = [
        {
            "columns": relation.columns,
            "definition": relation.definition,
            "parent_columns": relation.parent_columns,
            "parent_table": relation.parent_table,
            "table": relation.table,
            "virtual": relation.virtual,
        }
        for relation in sorted(
            related,
            key=lambda item: (
                item.table,
                item.columns,
                item.parent_table,
                item.parent_columns,
            ),
        )
    ]
    payload = {
        "database": schema.name,
        "table": {
            "columns": columns,
            "comment": table.comment,
            "name": table.name,
            "relations": relations,
            "table_type": table.table_type,
        },
    }
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
