"""Deterministic reviewer draft creation and schema refresh use case."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from metadata_pipeline.adapters.schema.tbls_json import TblsSchemaSource
from metadata_pipeline.domain.hashing import table_schema_hash
from metadata_pipeline.domain.review import (
    BusinessMetadata,
    ColumnReview,
    DocumentStatus,
    Evidence,
    EvidenceKind,
    EvidenceStatus,
    ReviewContractConfig,
    ReviewDocument,
)
from metadata_pipeline.io.review_yaml import (
    ReviewFileError,
    load_review_contract,
    load_review_document,
    write_review_document,
)
from metadata_pipeline.ports.schema_source import ColumnSchema, DatabaseSchema, TableSchema


class DraftAction(str, Enum):
    """Observable result of processing one raw or reviewer table."""

    CREATED = "created"
    UNCHANGED = "unchanged"
    REFRESHED = "refreshed"
    REQUIRES_MANUAL_REVIEW = "requires_manual_review"


@dataclass(frozen=True)
class DraftResult:
    """One deterministic draft outcome formatted later by the CLI."""

    table: str
    path: Path
    action: DraftAction
    issue_codes: tuple[str, ...] = ()


class DraftGenerationError(ValueError):
    """Raised when existing reviewer input is ambiguous or invalid."""


def create_review_drafts(
    schema_path: Path,
    review_dir: Path,
    contract_path: Path,
) -> tuple[DraftResult, ...]:
    """Create or refresh reviewer YAML without overwriting human-owned content."""
    schema = TblsSchemaSource(schema_path).load()
    contract = load_review_contract(contract_path)
    existing = _load_existing_reviews(review_dir)
    raw_tables = {table.name: table for table in schema.tables}
    schema_reference = _stable_schema_reference(schema_path, schema.name)
    results: list[DraftResult] = []

    for table_name in sorted(raw_tables):
        table = raw_tables[table_name]
        current = existing.get(table_name)
        if current is None:
            path = review_dir / f"{table_name}.yml"
            draft = _new_review_document(schema, table, contract, schema_reference)
            write_review_document(path, draft)
            results.append(DraftResult(table_name, path, DraftAction.CREATED))
            continue

        path, review = current
        results.append(_refresh_review(schema, table, review, path, contract, schema_reference))

    for orphaned_table in sorted(set(existing) - set(raw_tables)):
        path, _ = existing[orphaned_table]
        results.append(
            DraftResult(
                orphaned_table,
                path,
                DraftAction.REQUIRES_MANUAL_REVIEW,
                ("orphaned_review_table",),
            )
        )
    return tuple(results)


def _load_existing_reviews(review_dir: Path) -> dict[str, tuple[Path, ReviewDocument]]:
    reviews: dict[str, tuple[Path, ReviewDocument]] = {}
    paths = sorted((*review_dir.glob("*.yml"), *review_dir.glob("*.yaml")))
    for path in paths:
        try:
            review = load_review_document(path)
        except ReviewFileError as error:
            details = "; ".join(f"{issue.field}: {issue.message}" for issue in error.issues)
            raise DraftGenerationError(f"{path}: {details}") from error
        previous = reviews.get(review.table)
        if previous is not None:
            raise DraftGenerationError(
                f"{path}: duplicate review for table {review.table!r}; already defined by "
                f"{previous[0]}"
            )
        reviews[review.table] = (path, review)
    return reviews


def _new_review_document(
    schema: DatabaseSchema,
    table: TableSchema,
    contract: ReviewContractConfig,
    schema_reference: str,
) -> ReviewDocument:
    table_evidence = _technical_evidence(
        table.comment,
        f"{schema_reference}#tables.{table.name}.comment",
    )
    return ReviewDocument(
        contract_version=contract.contract_version,
        review_guideline_version=contract.review_guideline_version,
        transformation_guideline_version=contract.transformation_guideline_version,
        source_scope=contract.source_scope,
        database=schema.name,
        table=table.name,
        owner="unassigned",
        reviewer="unassigned",
        document_status=DocumentStatus.NEEDS_REVIEW,
        schema_hash=table_schema_hash(schema, table),
        business=BusinessMetadata(
            display_name=_display_name(table.name),
            description=table.comment or "Unknown — needs confirmation",
            grain="Unknown — needs confirmation",
            purpose=("Unknown — needs confirmation",),
            appropriate_use=("Unknown — needs confirmation",),
            inappropriate_use=("Unknown — needs confirmation",),
            freshness="Unknown — needs confirmation",
            caveats=("Business meaning requires domain reviewer confirmation.",),
            evidence=(table_evidence,),
        ),
        columns={
            column.name: _new_column_review(table, column, schema_reference)
            for column in sorted(table.columns, key=lambda item: item.name)
        },
        relationships=(),
        business_rules=(),
        data_quality=("Data quality expectations require reviewer confirmation.",),
        security=(),
    )


def _refresh_review(
    schema: DatabaseSchema,
    table: TableSchema,
    review: ReviewDocument,
    path: Path,
    contract: ReviewContractConfig,
    schema_reference: str,
) -> DraftResult:
    raw_columns = {column.name: column for column in table.columns}
    existing_columns = dict(review.columns)
    added_columns = sorted(set(raw_columns) - set(existing_columns))
    orphaned_columns = sorted(set(existing_columns) - set(raw_columns))
    for column_name in added_columns:
        existing_columns[column_name] = _new_column_review(
            table,
            raw_columns[column_name],
            schema_reference,
        )

    expected_hash = table_schema_hash(schema, table)
    contract_changed = (
        review.contract_version != contract.contract_version
        or review.review_guideline_version != contract.review_guideline_version
        or review.transformation_guideline_version != contract.transformation_guideline_version
    )
    needs_write = bool(added_columns) or review.schema_hash != expected_hash or contract_changed
    if needs_write:
        refreshed = review.model_copy(
            update={
                "contract_version": contract.contract_version,
                "review_guideline_version": contract.review_guideline_version,
                "transformation_guideline_version": contract.transformation_guideline_version,
                "document_status": DocumentStatus.NEEDS_REVIEW,
                "schema_hash": expected_hash,
                "columns": existing_columns,
            }
        )
        write_review_document(path, ReviewDocument.model_validate(refreshed.model_dump()))

    if orphaned_columns:
        return DraftResult(
            table.name,
            path,
            DraftAction.REQUIRES_MANUAL_REVIEW,
            tuple(f"orphaned_review_column:{column}" for column in orphaned_columns),
        )
    if needs_write:
        return DraftResult(table.name, path, DraftAction.REFRESHED)
    return DraftResult(table.name, path, DraftAction.UNCHANGED)


def _new_column_review(
    table: TableSchema,
    column: ColumnSchema,
    schema_reference: str,
) -> ColumnReview:
    semantic_type = _semantic_type(column)
    caveats: tuple[str, ...] = ()
    if semantic_type == "categorical":
        caveats = ("Allowed values require reviewer confirmation.",)
    return ColumnReview(
        business_name=_display_name(column.name),
        description=column.comment or "Unknown — needs confirmation",
        semantic_type=semantic_type,
        unit=_draft_unit(column, semantic_type),
        nullable_meaning=("Unknown — needs confirmation" if column.nullable else "not_applicable"),
        sensitivity=(
            "unknown"
            if semantic_type in {"email", "person_name", "phone", "address"}
            else "internal"
        ),
        allowed_values={},
        caveats=caveats,
        evidence=(
            _technical_evidence(
                column.comment,
                f"{schema_reference}#tables.{table.name}.columns.{column.name}",
            ),
        ),
    )


def _technical_evidence(comment: str, reference: str) -> Evidence:
    if comment:
        return Evidence(
            kind=EvidenceKind.CLICKHOUSE_COMMENT,
            reference=reference,
            status=EvidenceStatus.PROPOSED,
            note="Generated from the ClickHouse comment; domain confirmation is required.",
        )
    return Evidence(
        kind=EvidenceKind.UNKNOWN,
        reference=reference,
        status=EvidenceStatus.UNKNOWN,
        note="ClickHouse comment is missing; domain confirmation is required.",
    )


def _semantic_type(column: ColumnSchema) -> str:
    name = column.name.lower()
    data_type = column.data_type.lower()
    if "datetime" in data_type or data_type.startswith("date"):
        return "timestamp"
    if name == "email" or name.endswith("_email"):
        return "email"
    if name in {"full_name", "name"} or name.endswith("_name"):
        return "person_name"
    if "phone" in name:
        return "phone"
    if "address" in name:
        return "address"
    if name.endswith("_status") or name in {"status", "segment"}:
        return "categorical"
    if "decimal" in data_type or any(token in name for token in ("amount", "price")):
        return "monetary_amount"
    if any(token in name for token in ("quantity", "count")):
        return "count"
    if data_type == "uuid" or name.endswith("_id") or name.endswith("_code"):
        return "identifier"
    return "unknown"


def _draft_unit(column: ColumnSchema, semantic_type: str) -> str:
    comment = column.comment.lower()
    if semantic_type == "timestamp":
        return "UTC" if "utc" in comment else "Unknown — needs confirmation"
    if semantic_type == "monetary_amount":
        return "VND" if "vnd" in comment else "Unknown — needs confirmation"
    if semantic_type == "count":
        return "Unknown — needs confirmation"
    return "not_applicable"


def _display_name(value: str) -> str:
    return value.replace("_", " ").strip().title()


def _stable_schema_reference(schema_path: Path, database: str) -> str:
    if not schema_path.is_absolute():
        return schema_path.as_posix()
    try:
        return schema_path.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return f"catalog/{database}/generated/raw/schema.json"
