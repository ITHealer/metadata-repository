"""Unit tests for the strict reviewer metadata contract."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from metadata_pipeline.domain.review import DocumentStatus, ReviewDocument
from metadata_pipeline.io.review_yaml import load_review_document

REVIEW_DIR = Path("tests/fixtures/commerce_demo/review")


def test_review_document_rejects_unknown_fields() -> None:
    review = load_review_document(REVIEW_DIR / "customers.yml")
    payload = review.model_dump(mode="json")
    payload["invented_field"] = "not allowed"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ReviewDocument.model_validate(payload)


def test_document_status_alone_can_approve_unassigned_document() -> None:
    review = load_review_document(REVIEW_DIR / "customers.yml")
    payload = review.model_dump(mode="json")
    payload["document_status"] = DocumentStatus.APPROVED

    approved = ReviewDocument.model_validate(payload)

    assert approved.document_status is DocumentStatus.APPROVED
    assert approved.owner == "unassigned"
    assert approved.reviewer == "unassigned"


def test_relationship_requires_matching_column_counts() -> None:
    review = load_review_document(REVIEW_DIR / "orders.yml")
    payload = review.model_dump(mode="json")
    payload["relationships"][0]["to_columns"] = ["customer_id", "another_id"]

    with pytest.raises(
        ValidationError,
        match="from_columns and to_columns must contain the same number of items",
    ):
        ReviewDocument.model_validate(payload)
