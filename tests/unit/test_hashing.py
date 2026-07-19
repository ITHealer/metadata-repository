"""Tests for deterministic technical table hashes."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from metadata_pipeline.adapters.schema.tbls_json import TblsSchemaSource
from metadata_pipeline.domain.hashing import table_schema_hash
from metadata_pipeline.ports.schema_source import (
    ColumnSchema,
    DatabaseSchema,
    RelationSchema,
    TableSchema,
)


def _schema() -> tuple[DatabaseSchema, TableSchema]:
    columns = (
        ColumnSchema("order_id", "UUID", False, "Order identifier"),
        ColumnSchema("customer_id", "UUID", False, "Customer identifier"),
    )
    table = TableSchema("orders", "MergeTree", "One row per order", columns)
    customer = TableSchema(
        "customers",
        "MergeTree",
        "One row per customer",
        (ColumnSchema("customer_id", "UUID", False, "Customer identifier"),),
    )
    relation = RelationSchema(
        "orders",
        ("customer_id",),
        "customers",
        ("customer_id",),
        "orders.customer_id -> customers.customer_id",
        True,
    )
    secondary_relation = RelationSchema(
        "orders",
        ("order_id",),
        "customers",
        ("customer_id",),
        "orders.order_id -> customers.customer_id",
        True,
    )
    return (
        DatabaseSchema("demo", "Demo", (table, customer), (relation, secondary_relation)),
        table,
    )


def test_hash_ignores_column_and_relation_order() -> None:
    schema, table = _schema()
    reordered_table = replace(table, columns=tuple(reversed(table.columns)))
    reordered_schema = replace(
        schema,
        tables=tuple(reversed(schema.tables)),
        relations=tuple(reversed(schema.relations)),
    )

    assert table_schema_hash(schema, table) == table_schema_hash(reordered_schema, reordered_table)


def test_hash_changes_when_technical_comment_changes() -> None:
    schema, table = _schema()
    changed_table = replace(table, comment="Updated technical meaning")

    assert table_schema_hash(schema, table) != table_schema_hash(schema, changed_table)


def test_hash_changes_when_type_or_relation_changes() -> None:
    schema, table = _schema()
    changed_columns = (replace(table.columns[0], data_type="String"), *table.columns[1:])
    changed_table = replace(table, columns=changed_columns)
    changed_relation = replace(schema.relations[0], definition="changed join definition")
    changed_schema = replace(schema, relations=(changed_relation, *schema.relations[1:]))

    assert table_schema_hash(schema, table) != table_schema_hash(schema, changed_table)
    assert table_schema_hash(schema, table) != table_schema_hash(changed_schema, table)


def test_hash_ignores_source_json_key_order(tmp_path: Path) -> None:
    schema, _ = _schema()
    payload = {
        "name": schema.name,
        "desc": schema.description,
        "tables": [
            {
                "name": table.name,
                "type": table.table_type,
                "comment": table.comment,
                "columns": [
                    {
                        "name": column.name,
                        "type": column.data_type,
                        "nullable": column.nullable,
                        "comment": column.comment,
                    }
                    for column in table.columns
                ],
            }
            for table in schema.tables
        ],
        "relations": [
            {
                "table": relation.table,
                "columns": relation.columns,
                "parent_table": relation.parent_table,
                "parent_columns": relation.parent_columns,
                "def": relation.definition,
                "virtual": relation.virtual,
            }
            for relation in schema.relations
        ],
    }
    normal = tmp_path / "normal.json"
    reordered = tmp_path / "reordered.json"
    normal.write_text(json.dumps(payload), encoding="utf-8")
    reordered.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    normal_schema = TblsSchemaSource(normal).load()
    reordered_schema = TblsSchemaSource(reordered).load()

    assert table_schema_hash(normal_schema, normal_schema.tables[0]) == table_schema_hash(
        reordered_schema,
        reordered_schema.tables[0],
    )
