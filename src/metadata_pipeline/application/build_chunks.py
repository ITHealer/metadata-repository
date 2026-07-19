"""Build deterministic semantic chunks from structured published documents."""

from __future__ import annotations

import re

from metadata_pipeline.domain.published import (
    Chunk,
    ChunkType,
    Provenance,
    PublishedColumn,
    PublishedDocument,
    PublishedRelationship,
    PublishedRule,
)
from metadata_pipeline.domain.review import Evidence


def build_chunks(document: PublishedDocument) -> tuple[Chunk, ...]:
    """Create self-contained chunks without parsing rendered Markdown."""
    chunks = [_overview_chunk(document)]
    chunks.extend(_column_chunk(document, column) for column in document.columns)
    chunks.extend(_relationship_chunk(document, relation) for relation in document.relationships)
    chunks.extend(_rule_chunk(document, rule) for rule in document.business_rules)
    if document.data_quality or document.security or document.caveats:
        chunks.append(_quality_security_chunk(document))
    return tuple(sorted(chunks, key=lambda item: item.chunk_id))


def _overview_chunk(document: PublishedDocument) -> Chunk:
    content = "\n".join(
        (
            f"{document.qualified_name} — {document.summary}",
            f"Grain: {document.grain}",
            "Purpose: " + "; ".join(document.purpose),
            "Appropriate use: " + "; ".join(document.appropriate_use),
            "Inappropriate use: " + "; ".join(document.inappropriate_use),
            "Major caveats: " + ("; ".join(document.caveats) or "none supplied"),
        )
    )
    return _chunk(
        document,
        ChunkType.TABLE_OVERVIEW,
        "summary",
        content,
        document.business_evidence,
    )


def _column_chunk(document: PublishedDocument, column: PublishedColumn) -> Chunk:
    allowed_values = "; ".join(
        f"{value}={meaning}" for value, meaning in sorted(column.allowed_values.items())
    )
    content = "\n".join(
        (
            f"{document.qualified_name}.{column.name} — {column.business_name}",
            column.description,
            f"Technical type: {column.data_type}; nullable: {str(column.nullable).lower()}",
            f"Semantic type: {column.semantic_type}; unit/timezone: {column.unit}",
            f"Null meaning: {column.nullable_meaning}; sensitivity: {column.sensitivity}",
            "Allowed values: " + (allowed_values or "none supplied"),
            "Caveats: " + ("; ".join(column.caveats) or "none supplied"),
        )
    )
    return _chunk(
        document,
        ChunkType.COLUMN_GROUP,
        _semantic_key(column.name),
        content,
        column.evidence,
    )


def _relationship_chunk(
    document: PublishedDocument,
    relationship: PublishedRelationship,
) -> Chunk:
    content = "\n".join(
        (
            f"{document.qualified_name} relationship {relationship.name}",
            relationship.meaning,
            f"From {relationship.from_table}({', '.join(relationship.from_columns)})",
            f"To {relationship.to_table}({', '.join(relationship.to_columns)})",
            f"Join condition: {relationship.join_condition}",
            f"Cardinality: {relationship.cardinality.value}; "
            f"optional: {str(relationship.optional).lower()}",
            f"Row-count/duplicate risk: {relationship.row_count_impact.value}",
            "ClickHouse does not enforce this logical relationship as a foreign key.",
        )
    )
    return _chunk(
        document,
        ChunkType.RELATIONSHIP,
        _semantic_key(relationship.name),
        content,
        relationship.evidence,
    )


def _rule_chunk(document: PublishedDocument, rule: PublishedRule) -> Chunk:
    content = "\n".join(
        (
            f"{document.qualified_name} business rule: {rule.name}",
            rule.description,
            "Scope and exceptions are limited to the reviewer statement and evidence below.",
        )
    )
    return _chunk(
        document,
        ChunkType.BUSINESS_RULE,
        _semantic_key(rule.name),
        content,
        rule.evidence,
    )


def _quality_security_chunk(document: PublishedDocument) -> Chunk:
    content = "\n".join(
        (
            f"{document.qualified_name} quality and security guidance",
            "Data quality: " + ("; ".join(document.data_quality) or "none supplied"),
            "Security: " + ("; ".join(document.security) or "none supplied"),
            "Caveats: " + ("; ".join(document.caveats) or "none supplied"),
            "Safe use: follow inappropriate-use restrictions and resolve needs_review items "
            "before active indexing.",
        )
    )
    evidence = tuple(
        item
        for column in document.columns
        for item in column.evidence
        if column.sensitivity.lower() not in {"internal", "public"}
    )
    return _chunk(
        document,
        ChunkType.QUALITY_AND_SECURITY,
        "guidance",
        content,
        evidence,
    )


def _chunk(
    document: PublishedDocument,
    chunk_type: ChunkType,
    semantic_key: str,
    content: str,
    evidence: tuple[Evidence, ...],
) -> Chunk:
    qualified_name = document.qualified_name
    provenance: Provenance = document.provenance
    return Chunk(
        chunk_id=f"{qualified_name}::{chunk_type.value}::{semantic_key}",
        parent_document_id=f"{qualified_name}::document",
        semantic_key=semantic_key,
        chunk_type=chunk_type,
        database=document.database,
        table=document.table,
        qualified_name=qualified_name,
        document_status=document.document_status,
        index_eligible=document.index_eligible,
        schema_hash=document.schema_hash,
        contract_version=document.contract_version,
        review_guideline_version=document.review_guideline_version,
        transformation_guideline_version=document.transformation_guideline_version,
        source_review_path=provenance.source_review_path,
        source_review_commit=provenance.source_review_commit,
        generator_mode=provenance.generator_mode,
        generator_model=provenance.generator_model,
        prompt_version=provenance.prompt_version,
        content=content,
        evidence=evidence,
    )


def _semantic_key(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized or "item"
