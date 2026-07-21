"""Cross-file validation for reviewer metadata and raw tbls schema."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from metadata_pipeline.domain.hashing import table_schema_hash
from metadata_pipeline.domain.review import (
    DocumentStatus,
    Evidence,
    EvidenceStatus,
    ReviewContractConfig,
    ReviewDocument,
)
from metadata_pipeline.ports.schema_source import DatabaseSchema, TableSchema


class IssueSeverity(str, Enum):
    """Whether an issue blocks CI or only requires reviewer attention."""

    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class ValidationIssue:
    """One deterministic, actionable metadata validation result."""

    code: str
    path: Path
    field: str
    message: str
    severity: IssueSeverity = IssueSeverity.ERROR


def validate_review_document(
    schema: DatabaseSchema,
    review: ReviewDocument,
    contract: ReviewContractConfig,
    path: Path,
) -> tuple[ValidationIssue, ...]:
    """Validate one parsed review document against the live technical catalog."""
    issues: list[ValidationIssue] = []
    _require_equal(
        issues,
        path,
        "contract_version",
        review.contract_version,
        contract.contract_version,
        "contract version",
    )
    _require_equal(
        issues,
        path,
        "review_guideline_version",
        review.review_guideline_version,
        contract.review_guideline_version,
        "review guideline version",
    )
    _require_equal(
        issues,
        path,
        "transformation_guideline_version",
        review.transformation_guideline_version,
        contract.transformation_guideline_version,
        "transformation guideline version",
    )
    _require_equal(
        issues,
        path,
        "source_scope",
        review.source_scope,
        contract.source_scope,
        "source scope",
    )
    _require_equal(issues, path, "database", review.database, schema.name, "database")

    tables = {table.name: table for table in schema.tables}
    table = tables.get(review.table)
    if table is None:
        issues.append(
            ValidationIssue(
                "unknown_table",
                path,
                "table",
                f"table {review.table!r} does not exist in {schema.name!r}",
            )
        )
        return tuple(issues)

    _validate_schema_hash(issues, path, schema, table, review.schema_hash)
    available_columns = {column.name for column in table.columns}
    reviewed_columns = set(review.columns)
    for column_name in reviewed_columns:
        if column_name not in available_columns:
            issues.append(
                ValidationIssue(
                    "unknown_column",
                    path,
                    f"columns.{column_name}",
                    f"column {column_name!r} does not exist in table {review.table!r}",
                )
            )
    for column_name in sorted(available_columns - reviewed_columns):
        issues.append(
            ValidationIssue(
                "missing_column_review",
                path,
                f"columns.{column_name}",
                f"table {review.table!r} column {column_name!r} has no reviewer metadata",
            )
        )

    for index, relationship in enumerate(review.relationships):
        relationship_path = f"relationships.{index}"
        _validate_columns(
            issues,
            path,
            available_columns,
            relationship.from_columns,
            f"{relationship_path}.from_columns",
            review.table,
        )
        target_table = tables.get(relationship.to_table)
        if target_table is None:
            issues.append(
                ValidationIssue(
                    "unknown_relationship_table",
                    path,
                    f"{relationship_path}.to_table",
                    f"table {relationship.to_table!r} does not exist in {schema.name!r}",
                )
            )
            continue
        _validate_columns(
            issues,
            path,
            {column.name for column in target_table.columns},
            relationship.to_columns,
            f"{relationship_path}.to_columns",
            relationship.to_table,
        )

    _validate_review_semantics(issues, path, table, review)

    return tuple(issues)


def _validate_review_semantics(
    issues: list[ValidationIssue],
    path: Path,
    table: TableSchema,
    review: ReviewDocument,
) -> None:
    # Explicitly unknown business semantics are useful review findings, not contract errors.
    # Keep them visible after approval without forcing reviewers to invent facts to make CI pass.
    severity = IssueSeverity.WARNING
    _validate_evidence(issues, path, "business.evidence", review.business.evidence, review)
    raw_columns = {column.name: column for column in table.columns}
    for column_name, column_review in review.columns.items():
        raw_column = raw_columns.get(column_name)
        if raw_column is None:
            continue
        field = f"columns.{column_name}"
        semantic_type = column_review.semantic_type.lower()
        unit = column_review.unit.strip().lower()
        if _is_timestamp(raw_column.data_type) and _is_unknown_unit(unit):
            issues.append(
                ValidationIssue(
                    "missing_time_semantics",
                    path,
                    f"{field}.unit",
                    "timestamp column requires an explicit timezone or time unit",
                    severity,
                )
            )
        if semantic_type in {
            "monetary_amount",
            "measure",
            "count",
            "percentage",
            "duration",
        } and _is_unknown_unit(unit):
            issues.append(
                ValidationIssue(
                    "missing_measure_unit",
                    path,
                    f"{field}.unit",
                    f"semantic type {column_review.semantic_type!r} requires an explicit unit",
                    severity,
                )
            )
        if (
            semantic_type in {"categorical", "status", "code"}
            and not column_review.allowed_values
            and not column_review.caveats
        ):
            issues.append(
                ValidationIssue(
                    "missing_allowed_values",
                    path,
                    f"{field}.allowed_values",
                    "categorical column requires allowed values or an explicit caveat",
                    severity,
                )
            )
        if semantic_type in {"email", "person_name", "phone", "address"} and (
            column_review.sensitivity.strip().lower()
            in {"", "internal", "unknown", "not_applicable"}
        ):
            issues.append(
                ValidationIssue(
                    "missing_sensitivity_classification",
                    path,
                    f"{field}.sensitivity",
                    f"PII-like semantic type {column_review.semantic_type!r} "
                    "requires classification",
                    severity,
                )
            )
        _validate_evidence(
            issues,
            path,
            f"{field}.evidence",
            column_review.evidence,
            review,
        )

    for index, relationship in enumerate(review.relationships):
        _validate_evidence(
            issues,
            path,
            f"relationships.{index}.evidence",
            relationship.evidence,
            review,
        )
    for index, rule in enumerate(review.business_rules):
        _validate_evidence(
            issues,
            path,
            f"business_rules.{index}.evidence",
            rule.evidence,
            review,
        )


def _validate_evidence(
    issues: list[ValidationIssue],
    path: Path,
    field: str,
    evidence: tuple[Evidence, ...],
    review: ReviewDocument,
) -> None:
    severity = _approval_severity(review)
    if any(item.status is EvidenceStatus.CONFLICTING for item in evidence):
        issues.append(
            ValidationIssue(
                "conflicting_evidence",
                path,
                field,
                "conflicting evidence must be resolved before approval",
                severity,
            )
        )


def _approval_severity(review: ReviewDocument) -> IssueSeverity:
    if review.document_status is DocumentStatus.APPROVED:
        return IssueSeverity.ERROR
    return IssueSeverity.WARNING


def _is_timestamp(data_type: str) -> bool:
    normalized = data_type.lower()
    return "datetime" in normalized or normalized.startswith("date")


def _is_unknown_unit(unit: str) -> bool:
    return unit in {"", "not_applicable", "unknown", "unknown — needs confirmation"}


def _validate_schema_hash(
    issues: list[ValidationIssue],
    path: Path,
    schema: DatabaseSchema,
    table: TableSchema,
    actual: str,
) -> None:
    expected = table_schema_hash(schema, table)
    if actual != expected:
        issues.append(
            ValidationIssue(
                "stale_schema_hash",
                path,
                "schema_hash",
                f"expected {expected}, found {actual}",
            )
        )


def _validate_columns(
    issues: list[ValidationIssue],
    path: Path,
    available: set[str],
    columns: tuple[str, ...],
    field: str,
    table: str,
) -> None:
    for index, column in enumerate(columns):
        if column not in available:
            issues.append(
                ValidationIssue(
                    "unknown_relationship_column",
                    path,
                    f"{field}.{index}",
                    f"column {column!r} does not exist in table {table!r}",
                )
            )


def _require_equal(
    issues: list[ValidationIssue],
    path: Path,
    field: str,
    actual: str,
    expected: str,
    label: str,
) -> None:
    if actual != expected:
        issues.append(
            ValidationIssue(
                f"unexpected_{field}",
                path,
                field,
                f"expected {label} {expected!r}, found {actual!r}",
            )
        )
