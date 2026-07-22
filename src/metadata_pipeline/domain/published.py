"""Structured published metadata and retrieval chunk contracts."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import Field, model_validator

from metadata_pipeline.domain.review import (
    DocumentStatus,
    Evidence,
    RelationshipCardinality,
    RowCountImpact,
    StrictModel,
)


class GeneratorMode(str, Enum):
    """How a published document's narrative text was generated."""

    MOCK = "mock"
    LIVE = "live"


class ChunkType(str, Enum):
    """Semantic units allowed by the retrieval-v1 contract."""

    TABLE_OVERVIEW = "table_overview"
    COLUMN_GROUP = "column_group"
    RELATIONSHIP = "relationship"
    BUSINESS_RULE = "business_rule"
    QUALITY_AND_SECURITY = "quality_and_security"


class Provenance(StrictModel):
    """Auditable inputs and generator identity for one published document."""

    source_schema_path: str = Field(min_length=1)
    source_review_path: str = Field(min_length=1)
    source_review_commit: str = Field(pattern=r"^[0-9a-f]{7,64}$")
    generator_mode: GeneratorMode
    generator_model: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)


class PublishedColumn(StrictModel):
    """Raw technical column facts merged with reviewer-owned meaning."""

    name: str = Field(min_length=1)
    data_type: str = Field(min_length=1)
    nullable: bool
    technical_comment: str
    business_name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    semantic_type: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    nullable_meaning: str = Field(min_length=1)
    sensitivity: str = Field(min_length=1)
    allowed_values: dict[str, str] = Field(default_factory=dict)
    caveats: tuple[str, ...] = ()
    evidence: tuple[Evidence, ...] = Field(min_length=1)


class PublishedRelationship(StrictModel):
    """Self-contained join semantics with optional tbls technical context."""

    name: str = Field(min_length=1)
    from_table: str = Field(min_length=1)
    from_columns: tuple[str, ...] = Field(min_length=1)
    to_table: str = Field(min_length=1)
    to_columns: tuple[str, ...] = Field(min_length=1)
    join_condition: str = Field(min_length=1)
    cardinality: RelationshipCardinality
    optional: bool
    row_count_impact: RowCountImpact
    meaning: str = Field(min_length=1)
    # Pydantic evaluates model fields at runtime on Python 3.9, where ``X | None`` is invalid.
    technical_definition: Optional[str] = None  # noqa: UP007
    virtual: Optional[bool] = None  # noqa: UP007
    evidence: tuple[Evidence, ...] = Field(min_length=1)


class PublishedRule(StrictModel):
    """Reviewer-owned rule copied without strengthening its evidence."""

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    evidence: tuple[Evidence, ...] = Field(min_length=1)


class PublishedDocument(StrictModel):
    """Provider-neutral merge result consumed by renderers and chunkers."""

    document_id: str = Field(min_length=1)
    database: str = Field(min_length=1)
    table: str = Field(min_length=1)
    qualified_name: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    reviewer: str = Field(min_length=1)
    document_status: DocumentStatus
    index_eligible: bool
    schema_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    contract_version: str = Field(min_length=1)
    review_guideline_version: str = Field(min_length=1)
    transformation_guideline_version: str = Field(min_length=1)
    provenance: Provenance
    display_name: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    description: str = Field(min_length=1)
    grain: str = Field(min_length=1)
    purpose: tuple[str, ...] = Field(min_length=1)
    appropriate_use: tuple[str, ...] = Field(min_length=1)
    inappropriate_use: tuple[str, ...] = Field(min_length=1)
    aliases: tuple[str, ...] = ()
    freshness: str = Field(min_length=1)
    caveats: tuple[str, ...] = ()
    business_evidence: tuple[Evidence, ...] = Field(min_length=1)
    columns: tuple[PublishedColumn, ...] = Field(min_length=1)
    relationships: tuple[PublishedRelationship, ...] = ()
    business_rules: tuple[PublishedRule, ...] = ()
    data_quality: tuple[str, ...] = ()
    security: tuple[str, ...] = ()

    @model_validator(mode="after")
    def require_consistent_identity_and_eligibility(self) -> PublishedDocument:
        """Keep derived identity/status fields impossible to contradict."""
        expected_name = f"{self.database}.{self.table}"
        if self.document_id != expected_name or self.qualified_name != expected_name:
            raise ValueError("document_id and qualified_name must equal '<database>.<table>'")
        expected_eligibility = self.document_status is DocumentStatus.APPROVED
        if self.index_eligible is not expected_eligibility:
            raise ValueError("index_eligible must be true only for approved documents")
        if len({column.name for column in self.columns}) != len(self.columns):
            raise ValueError("published column names must be unique")
        return self


class Chunk(StrictModel):
    """One self-contained semantic retrieval unit."""

    chunk_id: str = Field(min_length=1)
    parent_document_id: str = Field(min_length=1)
    semantic_key: str = Field(min_length=1)
    chunk_type: ChunkType
    database: str = Field(min_length=1)
    table: str = Field(min_length=1)
    qualified_name: str = Field(min_length=1)
    document_status: DocumentStatus
    index_eligible: bool
    schema_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    contract_version: str = Field(min_length=1)
    review_guideline_version: str = Field(min_length=1)
    transformation_guideline_version: str = Field(min_length=1)
    source_review_path: str = Field(min_length=1)
    source_review_commit: str = Field(pattern=r"^[0-9a-f]{7,64}$")
    generator_mode: GeneratorMode
    generator_model: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    content: str = Field(min_length=1)
    evidence: tuple[Evidence, ...] = ()
    body_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def require_stable_identity(self) -> Chunk:
        """Validate IDs and index eligibility derived from document metadata."""
        qualified_name = f"{self.database}.{self.table}"
        if self.qualified_name != qualified_name:
            raise ValueError("qualified_name must equal '<database>.<table>'")
        if self.parent_document_id != f"{qualified_name}::document":
            raise ValueError("parent_document_id must reference the published document")
        expected_chunk_id = f"{qualified_name}::{self.chunk_type.value}::{self.semantic_key}"
        if self.chunk_id != expected_chunk_id:
            raise ValueError("chunk_id must match qualified name, chunk type, and semantic key")
        expected_eligibility = self.document_status is DocumentStatus.APPROVED
        if self.index_eligible is not expected_eligibility:
            raise ValueError("index_eligible must be true only for approved chunks")
        return self
