from pathlib import Path

import pytest

from metadata_pipeline.adapters.schema.tbls_json import TblsSchemaSource
from metadata_pipeline.ports.schema_source import SchemaSourceError

FIXTURE_PATH = Path("tests/fixtures/tbls/schema.json")


def test_loads_provider_neutral_schema_contract() -> None:
    schema = TblsSchemaSource(FIXTURE_PATH).load()

    assert schema.name == "contract_fixture"
    assert schema.description == "Small tbls contract fixture"
    assert [table.name for table in schema.tables] == ["parents", "children"]

    children = schema.tables[1]
    assert children.comment == "One row per child."
    assert [(column.name, column.data_type) for column in children.columns] == [
        ("child_id", "UUID"),
        ("parent_id", "UUID"),
    ]
    assert children.columns[1].comment == "Logical parent reference."

    relation = schema.relations[0]
    assert relation.table == "children"
    assert relation.columns == ("parent_id",)
    assert relation.parent_table == "parents"
    assert relation.parent_columns == ("parent_id",)
    assert relation.virtual is True


def test_reports_file_and_field_for_invalid_contract(tmp_path: Path) -> None:
    invalid_path = tmp_path / "schema.json"
    invalid_path.write_text(
        '{"name":"broken","tables":[{"name":"orders","type":"BASE TABLE",'
        '"columns":[{"type":"UUID","nullable":false}]}]}',
        encoding="utf-8",
    )

    with pytest.raises(SchemaSourceError) as error:
        TblsSchemaSource(invalid_path).load()

    message = str(error.value)
    assert str(invalid_path) in message
    assert "tables[0].columns[0].name: missing required field" in message


def test_rejects_relation_to_unknown_column(tmp_path: Path) -> None:
    invalid_path = tmp_path / "schema.json"
    invalid_path.write_text(
        '{"name":"broken","tables":[{"name":"orders","type":"BASE TABLE",'
        '"columns":[{"name":"order_id","type":"UUID","nullable":false}]}],'
        '"relations":[{"table":"orders","columns":["customer_id"],'
        '"parent_table":"orders","parent_columns":["order_id"],'
        '"def":"invalid","virtual":true}]}',
        encoding="utf-8",
    )

    with pytest.raises(SchemaSourceError, match=r"relations\[0\]\.columns\[0\]"):
        TblsSchemaSource(invalid_path).load()
