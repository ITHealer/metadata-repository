"""Tests for approval-aware reviewer validation rules."""

from __future__ import annotations

from pathlib import Path

import pytest

from metadata_pipeline.adapters.schema.tbls_json import TblsSchemaSource
from metadata_pipeline.domain.review import DocumentStatus, Evidence, EvidenceStatus, ReviewDocument
from metadata_pipeline.io.review_yaml import load_review_contract, load_review_document
from metadata_pipeline.validation.review import (
    IssueSeverity,
    ValidationIssue,
    validate_review_document,
)

SCHEMA = TblsSchemaSource(Path("tests/fixtures/commerce_demo/schema.json")).load()
CONTRACT = load_review_contract(Path("contracts/metadata_contract.yml"))
REVIEW_DIR = Path("tests/fixtures/commerce_demo/review")


def _confirmed(review: ReviewDocument) -> ReviewDocument:
    def confirmed_evidence(items: tuple[Evidence, ...]) -> tuple[Evidence, ...]:
        return tuple(item.model_copy(update={"status": EvidenceStatus.CONFIRMED}) for item in items)

    business = review.business.model_copy(
        update={"evidence": confirmed_evidence(review.business.evidence)}
    )
    columns = {
        name: column.model_copy(update={"evidence": confirmed_evidence(column.evidence)})
        for name, column in review.columns.items()
    }
    relationships = tuple(
        relationship.model_copy(update={"evidence": confirmed_evidence(relationship.evidence)})
        for relationship in review.relationships
    )
    rules = tuple(
        rule.model_copy(update={"evidence": confirmed_evidence(rule.evidence)})
        for rule in review.business_rules
    )
    return review.model_copy(
        update={
            "owner": "commerce-team",
            "reviewer": "domain-reviewer",
            "document_status": DocumentStatus.APPROVED,
            "business": business,
            "columns": columns,
            "relationships": relationships,
            "business_rules": rules,
        }
    )


def _issues(review: ReviewDocument, filename: str) -> tuple[ValidationIssue, ...]:
    return validate_review_document(SCHEMA, review, CONTRACT, REVIEW_DIR / filename)


def test_fully_confirmed_approved_review_passes() -> None:
    assert _issues(_confirmed(load_review_document(REVIEW_DIR / "orders.yml")), "orders.yml") == ()


def test_needs_review_conditional_gap_is_warning_but_approved_is_error() -> None:
    review = load_review_document(REVIEW_DIR / "orders.yml").model_copy(
        update={"document_status": DocumentStatus.NEEDS_REVIEW}
    )
    columns = dict(review.columns)
    columns["total_amount"] = columns["total_amount"].model_copy(update={"unit": "not_applicable"})
    needs_review = review.model_copy(update={"columns": columns})
    warning = next(
        issue
        for issue in _issues(needs_review, "orders.yml")
        if issue.code == "missing_measure_unit"
    )

    approved = _confirmed(needs_review)
    error = next(
        issue for issue in _issues(approved, "orders.yml") if issue.code == "missing_measure_unit"
    )

    assert warning.severity is IssueSeverity.WARNING
    assert error.severity is IssueSeverity.ERROR


def test_approved_review_accepts_proposed_evidence() -> None:
    review = load_review_document(REVIEW_DIR / "orders.yml")

    def proposed(items: tuple[Evidence, ...]) -> tuple[Evidence, ...]:
        return tuple(item.model_copy(update={"status": EvidenceStatus.PROPOSED}) for item in items)

    proposed_business = review.business.model_copy(
        update={"evidence": proposed(review.business.evidence)}
    )
    review = review.model_copy(
        update={
            "owner": "commerce-team",
            "reviewer": "domain-reviewer",
            "document_status": DocumentStatus.APPROVED,
            "business": proposed_business,
            "columns": {
                name: column.model_copy(update={"evidence": proposed(column.evidence)})
                for name, column in review.columns.items()
            },
            "relationships": tuple(
                relationship.model_copy(update={"evidence": proposed(relationship.evidence)})
                for relationship in review.relationships
            ),
            "business_rules": tuple(
                rule.model_copy(update={"evidence": proposed(rule.evidence)})
                for rule in review.business_rules
            ),
        }
    )

    assert _issues(review, "orders.yml") == ()


def test_conflicting_evidence_blocks_approval() -> None:
    review = _confirmed(load_review_document(REVIEW_DIR / "orders.yml"))
    evidence = list(review.business.evidence)
    evidence[0] = evidence[0].model_copy(update={"status": EvidenceStatus.CONFLICTING})
    review = review.model_copy(
        update={"business": review.business.model_copy(update={"evidence": tuple(evidence)})}
    )

    issue = next(
        issue for issue in _issues(review, "orders.yml") if issue.code == "conflicting_evidence"
    )

    assert issue.severity is IssueSeverity.ERROR


@pytest.mark.parametrize(
    ("filename", "column_name", "updates", "expected_code"),
    [
        ("orders.yml", "created_at", {"unit": "not_applicable"}, "missing_time_semantics"),
        (
            "orders.yml",
            "order_status",
            {"allowed_values": {}, "caveats": ()},
            "missing_allowed_values",
        ),
        (
            "customers.yml",
            "email",
            {"sensitivity": "internal"},
            "missing_sensitivity_classification",
        ),
    ],
)
def test_conditional_rules_report_actionable_warning(
    filename: str,
    column_name: str,
    updates: dict[str, object],
    expected_code: str,
) -> None:
    review = load_review_document(REVIEW_DIR / filename).model_copy(
        update={"document_status": DocumentStatus.NEEDS_REVIEW}
    )
    columns = dict(review.columns)
    columns[column_name] = columns[column_name].model_copy(update=updates)

    issue = next(
        issue
        for issue in _issues(review.model_copy(update={"columns": columns}), filename)
        if issue.code == expected_code
    )

    assert issue.severity is IssueSeverity.WARNING
