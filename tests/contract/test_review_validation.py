"""Contract tests for reviewer metadata against raw tbls schema.json."""

from __future__ import annotations

import json
from pathlib import Path

from metadata_pipeline.adapters.schema.tbls_json import TblsSchemaSource
from metadata_pipeline.application.review_contract import (
    export_review_json_schema,
    validate_review_directory,
)
from metadata_pipeline.io.review_yaml import load_review_contract, load_review_document
from metadata_pipeline.validation.review import validate_review_document

SCHEMA_PATH = Path("schema/raw/commerce_demo/schema.json")
REVIEW_DIR = Path("metadata/review/commerce_demo")
CONTRACT_PATH = Path("config/metadata_contract.yml")


def _issue_codes(review_file: str, **updates: object) -> set[str]:
    schema = TblsSchemaSource(SCHEMA_PATH).load()
    contract = load_review_contract(CONTRACT_PATH)
    review = load_review_document(REVIEW_DIR / review_file).model_copy(update=updates)
    issues = validate_review_document(schema, review, contract, REVIEW_DIR / review_file)
    return {issue.code for issue in issues}


def test_committed_review_directory_matches_raw_schema() -> None:
    assert validate_review_directory(SCHEMA_PATH, REVIEW_DIR, CONTRACT_PATH) == ()


def test_reviewer_cannot_declare_unknown_table() -> None:
    assert "unknown_table" in _issue_codes("customers.yml", table="customer_typo")


def test_reviewer_cannot_declare_unknown_column() -> None:
    review = load_review_document(REVIEW_DIR / "customers.yml")
    columns = dict(review.columns)
    columns["customer_typo"] = columns["customer_id"]

    assert "unknown_column" in _issue_codes("customers.yml", columns=columns)


def test_reviewer_cannot_declare_unknown_relationship_table() -> None:
    review = load_review_document(REVIEW_DIR / "orders.yml")
    relationship = review.relationships[0].model_copy(update={"to_table": "customer_typo"})

    assert "unknown_relationship_table" in _issue_codes("orders.yml", relationships=(relationship,))


def test_reviewer_cannot_declare_unknown_relationship_column() -> None:
    review = load_review_document(REVIEW_DIR / "orders.yml")
    relationship = review.relationships[0].model_copy(update={"from_columns": ("customer_typo",)})

    assert "unknown_relationship_column" in _issue_codes(
        "orders.yml", relationships=(relationship,)
    )


def test_changed_raw_schema_invalidates_review_hash() -> None:
    assert "stale_schema_hash" in _issue_codes("customers.yml", schema_hash="0" * 64)


def test_exported_json_schema_is_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    export_review_json_schema(first)
    export_review_json_schema(second)

    assert first.read_bytes() == second.read_bytes()
    schema = json.loads(first.read_text(encoding="utf-8"))
    assert schema["additionalProperties"] is False
    assert schema["properties"]["source_scope"]["const"] == "clickhouse"
