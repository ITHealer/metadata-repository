"""Validated reviewer-owned metadata contract."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    """Base model that rejects undeclared reviewer fields."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class DocumentStatus(str, Enum):
    """Human review lifecycle state."""

    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"


class EvidenceStatus(str, Enum):
    """Confidence attached to a reviewer claim."""

    CONFIRMED = "confirmed"
    PROPOSED = "proposed"
    UNKNOWN = "unknown"
    CONFLICTING = "conflicting"


class EvidenceKind(str, Enum):
    """Auditable source supporting a metadata claim."""

    CLICKHOUSE_DDL = "clickhouse_ddl"
    CLICKHOUSE_COMMENT = "clickhouse_comment"
    TBLS_RELATION = "tbls_relation"
    VALIDATION_QUERY = "validation_query"
    DASHBOARD = "dashboard"
    TICKET = "ticket"
    POLICY = "policy"
    OWNER_CONFIRMATION = "owner_confirmation"
    UNKNOWN = "unknown"


class RelationshipCardinality(str, Enum):
    """Expected cardinality of a documented join."""

    ONE_TO_ONE = "one_to_one"
    ONE_TO_MANY = "one_to_many"
    MANY_TO_ONE = "many_to_one"
    MANY_TO_MANY = "many_to_many"
    UNKNOWN = "unknown"


class RowCountImpact(str, Enum):
    """Expected effect of a join on the source row count."""

    PRESERVES = "preserves"
    MAY_INCREASE = "may_increase"
    MAY_DECREASE = "may_decrease"
    UNKNOWN = "unknown"


class Evidence(StrictModel):
    """Reference and confidence for one reviewer claim."""

    kind: EvidenceKind
    reference: str = Field(min_length=1)
    status: EvidenceStatus
    note: str = ""


class BusinessMetadata(StrictModel):
    """Business-level meaning and intended usage of a table."""

    display_name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    grain: str = Field(min_length=1)
    purpose: tuple[str, ...] = Field(min_length=1)
    appropriate_use: tuple[str, ...] = Field(min_length=1)
    inappropriate_use: tuple[str, ...] = Field(min_length=1)
    aliases: tuple[str, ...] = ()
    freshness: str = "Unknown — needs confirmation"
    caveats: tuple[str, ...] = ()
    evidence: tuple[Evidence, ...] = Field(min_length=1)


class ColumnReview(StrictModel):
    """Reviewer-owned business meaning for one technical column."""

    business_name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    semantic_type: str = Field(min_length=1)
    unit: str = "not_applicable"
    nullable_meaning: str = "not_applicable"
    sensitivity: str = "internal"
    allowed_values: dict[str, str] = Field(default_factory=dict)
    caveats: tuple[str, ...] = ()
    evidence: tuple[Evidence, ...] = Field(min_length=1)


class RelationshipReview(StrictModel):
    """Reviewer-owned join semantics between two ClickHouse tables."""

    name: str = Field(min_length=1)
    from_columns: tuple[str, ...] = Field(min_length=1)
    to_table: str = Field(min_length=1)
    to_columns: tuple[str, ...] = Field(min_length=1)
    join_condition: str = Field(min_length=1)
    cardinality: RelationshipCardinality
    optional: bool
    row_count_impact: RowCountImpact
    meaning: str = Field(min_length=1)
    evidence: tuple[Evidence, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_matching_column_counts(self) -> RelationshipReview:
        """Require each source join column to have one target column."""
        if len(self.from_columns) != len(self.to_columns):
            raise ValueError("from_columns and to_columns must contain the same number of items")
        return self


class BusinessRule(StrictModel):
    """Filter, formula, mapping, or usage rule supplied by a reviewer."""

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    evidence: tuple[Evidence, ...] = Field(min_length=1)


class ReviewDocument(StrictModel):
    """Complete reviewer contract for one ClickHouse table."""

    contract_version: str = Field(min_length=1)
    review_guideline_version: str = Field(min_length=1)
    transformation_guideline_version: str = Field(min_length=1)
    source_scope: Literal["clickhouse"]
    database: str = Field(min_length=1)
    table: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    reviewer: str = Field(min_length=1)
    document_status: DocumentStatus
    schema_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    business: BusinessMetadata
    columns: dict[str, ColumnReview] = Field(min_length=1)
    relationships: tuple[RelationshipReview, ...] = ()
    business_rules: tuple[BusinessRule, ...] = ()
    data_quality: tuple[str, ...] = ()
    security: tuple[str, ...] = ()


class ReviewContractConfig(StrictModel):
    """Version settings shared by review files and validators."""

    contract_version: str = Field(min_length=1)
    review_guideline_version: str = Field(min_length=1)
    transformation_guideline_version: str = Field(min_length=1)
    source_scope: Literal["clickhouse"]
