"""Unit tests for deterministic reviewer draft generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from metadata_pipeline.application.create_drafts import DraftAction, create_review_drafts
from metadata_pipeline.domain.review import DocumentStatus
from metadata_pipeline.io.review_yaml import load_review_document, write_review_document

SCHEMA_PATH = Path("schema/raw/commerce_demo/schema.json")
CONTRACT_PATH = Path("config/metadata_contract.yml")


def _changed_schema(tmp_path: Path, mutate: str) -> Path:
    payload: dict[str, Any] = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    customers = next(table for table in payload["tables"] if table["name"] == "customers")
    if mutate == "add_column":
        customers["columns"].append(
            {
                "name": "channel",
                "type": "String",
                "nullable": False,
                "comment": "Technical acquisition channel",
            }
        )
    elif mutate == "remove_column":
        customers["columns"] = [
            column for column in customers["columns"] if column["name"] != "segment"
        ]
    elif mutate == "remove_table":
        payload["tables"] = [table for table in payload["tables"] if table["name"] != "customers"]
        payload["relations"] = [
            relation
            for relation in payload["relations"]
            if relation["table"] != "customers" and relation["parent_table"] != "customers"
        ]
    output = tmp_path / f"schema-{mutate}.json"
    output.write_text(json.dumps(payload), encoding="utf-8")
    return output


def test_creates_valid_drafts_and_second_run_is_unchanged(tmp_path: Path) -> None:
    review_dir = tmp_path / "review"

    first = create_review_drafts(SCHEMA_PATH, review_dir, CONTRACT_PATH)
    before = {path.name: path.read_bytes() for path in review_dir.glob("*.yml")}
    second = create_review_drafts(SCHEMA_PATH, review_dir, CONTRACT_PATH)

    assert {result.action for result in first} == {DraftAction.CREATED}
    assert {result.action for result in second} == {DraftAction.UNCHANGED}
    assert {path.name: path.read_bytes() for path in review_dir.glob("*.yml")} == before
    assert load_review_document(review_dir / "customers.yml").owner == "unassigned"


def test_schema_refresh_preserves_human_content_and_adds_column(tmp_path: Path) -> None:
    review_dir = tmp_path / "review"
    create_review_drafts(SCHEMA_PATH, review_dir, CONTRACT_PATH)
    path = review_dir / "customers.yml"
    review = load_review_document(path)
    custom_purpose = ("Reviewer-owned customer analytics purpose.",)
    reviewed = review.model_copy(
        update={
            "owner": "customer-team",
            "reviewer": "domain-reviewer",
            "document_status": DocumentStatus.APPROVED,
            "business": review.business.model_copy(update={"purpose": custom_purpose}),
        }
    )
    write_review_document(path, reviewed)

    results = create_review_drafts(
        _changed_schema(tmp_path, "add_column"), review_dir, CONTRACT_PATH
    )
    refreshed = load_review_document(path)

    customer_result = next(result for result in results if result.table == "customers")
    assert customer_result.action is DraftAction.REFRESHED
    assert refreshed.business.purpose == custom_purpose
    assert refreshed.owner == "customer-team"
    assert refreshed.document_status is DocumentStatus.NEEDS_REVIEW
    assert "channel" in refreshed.columns
    assert (
        refreshed.columns["channel"]
        .evidence[0]
        .reference.startswith("schema/raw/commerce_demo/schema.json#")
    )


def test_removed_column_is_preserved_for_manual_review(tmp_path: Path) -> None:
    review_dir = tmp_path / "review"
    create_review_drafts(SCHEMA_PATH, review_dir, CONTRACT_PATH)

    results = create_review_drafts(
        _changed_schema(tmp_path, "remove_column"), review_dir, CONTRACT_PATH
    )
    customer_result = next(result for result in results if result.table == "customers")

    assert customer_result.action is DraftAction.REQUIRES_MANUAL_REVIEW
    assert customer_result.issue_codes == ("orphaned_review_column:segment",)
    assert "segment" in load_review_document(review_dir / "customers.yml").columns


def test_removed_table_file_is_not_deleted(tmp_path: Path) -> None:
    review_dir = tmp_path / "review"
    create_review_drafts(SCHEMA_PATH, review_dir, CONTRACT_PATH)
    customer_path = review_dir / "customers.yml"

    results = create_review_drafts(
        _changed_schema(tmp_path, "remove_table"), review_dir, CONTRACT_PATH
    )
    customer_result = next(result for result in results if result.table == "customers")

    assert customer_result.action is DraftAction.REQUIRES_MANUAL_REVIEW
    assert customer_result.issue_codes == ("orphaned_review_table",)
    assert customer_path.exists()
