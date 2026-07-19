"""Tests for deterministic schema synchronization summaries."""

from dataclasses import replace
from pathlib import Path

from metadata_pipeline.adapters.schema.tbls_json import TblsSchemaSource
from metadata_pipeline.application.schema_sync_summary import (
    render_schema_sync_pr_body,
    summarize_schema_change,
)
from metadata_pipeline.ports.schema_source import ColumnSchema, TableSchema


def test_additive_schema_scenario_lists_tables_and_reviewer_files() -> None:
    before = TblsSchemaSource(Path("schema/raw/commerce_demo/schema.json")).load()
    orders = next(table for table in before.tables if table.name == "orders")
    changed_orders = replace(
        orders,
        columns=orders.columns
        + (
            ColumnSchema(
                name="channel",
                data_type="LowCardinality(String)",
                nullable=False,
                comment="Order acquisition channel: web, mobile, or partner",
            ),
        ),
    )
    event_table = TableSchema(
        name="order_events",
        table_type="BASE TABLE",
        comment="Synthetic order lifecycle events.",
        columns=(
            ColumnSchema("event_id", "UUID", False, "Stable event identifier"),
            ColumnSchema("order_id", "UUID", False, "Associated order identifier"),
        ),
    )
    after = replace(
        before,
        tables=tuple(changed_orders if table.name == "orders" else table for table in before.tables)
        + (event_table,),
    )

    summary = summarize_schema_change(before, after)

    assert summary.added == ("order_events",)
    assert summary.modified == ("orders",)
    assert summary.deleted == ()
    assert summary.review_files == (
        "metadata/review/commerce_demo/order_events.yml",
        "metadata/review/commerce_demo/orders.yml",
    )
    body = render_schema_sync_pr_body(summary)
    assert "| Added | `order_events` |" in body
    assert "| Modified | `orders` |" in body


def test_deleted_table_remains_in_reviewer_attention() -> None:
    before = TblsSchemaSource(Path("schema/raw/commerce_demo/schema.json")).load()
    after = replace(
        before,
        tables=tuple(table for table in before.tables if table.name != "customers"),
        relations=tuple(
            relation
            for relation in before.relations
            if relation.table != "customers" and relation.parent_table != "customers"
        ),
    )

    summary = summarize_schema_change(before, after)

    assert summary.deleted == ("customers",)
    assert summary.modified == ("orders",)
    assert summary.review_files == (
        "metadata/review/commerce_demo/customers.yml",
        "metadata/review/commerce_demo/orders.yml",
    )
