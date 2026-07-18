import os
from pathlib import Path

import pytest

from metadata_pipeline.adapters.schema.tbls_json import TblsSchemaSource

RAW_SCHEMA_PATH = Path("schema/raw/commerce_demo")

pytestmark = [
    pytest.mark.schema_integration,
    pytest.mark.skipif(
        os.getenv("RUN_TBLS_INTEGRATION") != "1",
        reason="set RUN_TBLS_INTEGRATION=1 after generating tbls documentation",
    ),
]


def test_generated_schema_contains_comments_and_virtual_relations() -> None:
    schema = TblsSchemaSource(RAW_SCHEMA_PATH / "schema.json").load()
    tables = {table.name: table for table in schema.tables}

    assert set(tables) == {"customers", "orders", "order_items"}
    assert all(table.comment.strip() for table in tables.values())
    assert all(column.comment.strip() for table in tables.values() for column in table.columns)

    relations = {
        (relation.table, relation.columns, relation.parent_table, relation.parent_columns)
        for relation in schema.relations
    }
    assert relations == {
        ("orders", ("customer_id",), "customers", ("customer_id",)),
        ("order_items", ("order_id",), "orders", ("order_id",)),
    }
    assert all(relation.virtual for relation in schema.relations)


def test_generated_documentation_contains_er_diagram_and_no_credentials() -> None:
    assert (RAW_SCHEMA_PATH / "README.md").is_file()
    assert (RAW_SCHEMA_PATH / "schema.json").is_file()

    generated_text = "\n".join(
        path.read_text(encoding="utf-8") for path in RAW_SCHEMA_PATH.rglob("*") if path.is_file()
    )
    assert "```mermaid" in generated_text
    assert "erDiagram" in generated_text
    assert "Order fact at one row per order_id" in generated_text
    assert "demo_password" not in generated_text
    assert "clickhouse://demo:" not in generated_text
