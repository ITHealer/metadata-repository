"""Co-location and source-contract validation for semantic chunks."""

from __future__ import annotations

from pathlib import Path

from metadata_pipeline.domain.hashing import canonical_sha256
from metadata_pipeline.domain.published import Chunk, ChunkType, PublishedDocument
from metadata_pipeline.validation.review import ValidationIssue


def validate_chunks(
    document: PublishedDocument,
    chunks: tuple[Chunk, ...],
    path: Path,
) -> tuple[ValidationIssue, ...]:
    """Validate chunk identity, coverage, and required self-contained facts."""
    issues: list[ValidationIssue] = []
    ids = [chunk.chunk_id for chunk in chunks]
    if len(ids) != len(set(ids)):
        issues.append(
            ValidationIssue("duplicate_chunk_id", path, "chunk_id", "chunk IDs must be unique")
        )
    overview = [chunk for chunk in chunks if chunk.chunk_type is ChunkType.TABLE_OVERVIEW]
    if len(overview) != 1:
        issues.append(
            ValidationIssue(
                "invalid_overview_count",
                path,
                "table_overview",
                "exactly one table overview chunk is required",
            )
        )
    expected_parent = f"{document.document_id}::document"
    for chunk in chunks:
        expected_hash = canonical_sha256(chunk.model_dump(mode="json", exclude={"body_hash"}))
        if chunk.body_hash != expected_hash:
            issues.append(
                ValidationIssue(
                    "invalid_chunk_body_hash",
                    path,
                    chunk.chunk_id,
                    "body_hash does not match index-relevant chunk content",
                )
            )
        if chunk.parent_document_id != expected_parent:
            issues.append(
                ValidationIssue(
                    "invalid_chunk_parent",
                    path,
                    chunk.chunk_id,
                    f"expected parent {expected_parent!r}",
                )
            )
        if document.qualified_name not in chunk.content:
            issues.append(
                ValidationIssue(
                    "missing_chunk_context",
                    path,
                    chunk.chunk_id,
                    "chunk content must include the qualified table name",
                )
            )
    for column in document.columns:
        expected_id = (
            f"{document.qualified_name}::{ChunkType.COLUMN_GROUP.value}::"
            f"{_semantic_key(column.name)}"
        )
        matches = [
            chunk
            for chunk in chunks
            if chunk.chunk_type is ChunkType.COLUMN_GROUP and chunk.chunk_id == expected_id
        ]
        if len(matches) != 1:
            issues.append(
                ValidationIssue(
                    "missing_column_chunk",
                    path,
                    f"columns.{column.name}",
                    "each published column requires exactly one column chunk",
                )
            )
            continue
        column_required = (
            column.data_type,
            column.semantic_type,
            column.unit,
            column.description,
        )
        _require_content(
            issues,
            path,
            matches[0],
            column_required,
            "incomplete_column_context",
        )
    for relationship in document.relationships:
        expected_id = (
            f"{document.qualified_name}::{ChunkType.RELATIONSHIP.value}::"
            f"{_semantic_key(relationship.name)}"
        )
        matches = [
            chunk
            for chunk in chunks
            if chunk.chunk_type is ChunkType.RELATIONSHIP and chunk.chunk_id == expected_id
        ]
        if len(matches) != 1:
            issues.append(
                ValidationIssue(
                    "missing_relationship_chunk",
                    path,
                    f"relationships.{relationship.name}",
                    "each relationship requires exactly one relationship chunk",
                )
            )
            continue
        relationship_required = (
            relationship.from_table,
            relationship.to_table,
            relationship.join_condition,
            relationship.cardinality.value,
            relationship.row_count_impact.value,
        )
        _require_content(
            issues,
            path,
            matches[0],
            relationship_required,
            "incomplete_relationship_context",
        )
    return tuple(issues)


def _require_content(
    issues: list[ValidationIssue],
    path: Path,
    chunk: Chunk,
    required: tuple[str, ...],
    code: str,
) -> None:
    missing = tuple(value for value in required if value not in chunk.content)
    if missing:
        issues.append(
            ValidationIssue(
                code,
                path,
                chunk.chunk_id,
                "chunk is missing required context: " + ", ".join(repr(item) for item in missing),
            )
        )


def _semantic_key(value: str) -> str:
    import re

    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized or "item"
