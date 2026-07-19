"""Cross-file validation for reviewer metadata and raw tbls schema."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from metadata_pipeline.domain.hashing import table_schema_hash
from metadata_pipeline.domain.review import ReviewContractConfig, ReviewDocument
from metadata_pipeline.ports.schema_source import DatabaseSchema, TableSchema


@dataclass(frozen=True)
class ValidationIssue:
    """One deterministic, actionable metadata validation failure."""

    code: str
    path: Path
    field: str
    message: str


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
    for column_name in review.columns:
        if column_name not in available_columns:
            issues.append(
                ValidationIssue(
                    "unknown_column",
                    path,
                    f"columns.{column_name}",
                    f"column {column_name!r} does not exist in table {review.table!r}",
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

    return tuple(issues)


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
