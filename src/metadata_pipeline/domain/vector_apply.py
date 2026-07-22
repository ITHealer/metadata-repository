"""Versioned results for VectorDB bootstrap and apply operations."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import Field, model_validator

from metadata_pipeline.domain.review import StrictModel


class ApplyOutcome(str, Enum):
    """Index apply results that distinguish no-op from disabled."""

    APPLIED = "applied"
    DISABLED = "disabled"
    NOOP = "noop"


class VectorApplySummary(StrictModel):
    """Actual operation counts written only after state verification."""

    format_version: Literal["vector-apply-summary-v1"] = "vector-apply-summary-v1"
    outcome: ApplyOutcome
    collection: str = Field(min_length=1)
    manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    document_count: int = Field(ge=0)
    chunk_count: int = Field(ge=0)
    upserted_count: int = Field(ge=0)
    deleted_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    verified: bool

    @model_validator(mode="after")
    def require_consistent_outcome(self) -> VectorApplySummary:
        changed = self.upserted_count + self.deleted_count
        if self.outcome is ApplyOutcome.APPLIED and (not changed or not self.verified):
            raise ValueError("applied outcome requires changes and successful verification")
        if self.outcome is ApplyOutcome.NOOP and (changed or not self.verified):
            raise ValueError("noop outcome requires zero changes and successful verification")
        if self.outcome is ApplyOutcome.DISABLED and (changed or self.verified):
            raise ValueError("disabled outcome cannot claim mutations or verification")
        return self
