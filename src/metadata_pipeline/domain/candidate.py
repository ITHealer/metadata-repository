"""Persistent generated-candidate contract and lifecycle states."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import Field, model_validator

from metadata_pipeline.domain.published import PublishedDocument
from metadata_pipeline.domain.review import DocumentStatus, StrictModel


class CandidateState(str, Enum):
    """Whether a generated candidate is awaiting review or safely promoted."""

    REVIEW = "review"
    PROMOTED = "promoted"


class GenerationFingerprint(StrictModel):
    """Every input that can materially change generated narrative output."""

    schema_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    review_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    contract_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    guideline_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    generator_model: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class GeneratedCandidate(StrictModel):
    """Machine-readable source for one reviewer-visible Markdown candidate."""

    artifact_version: Literal["candidate-v1"] = "candidate-v1"
    database: str = Field(min_length=1)
    table: str = Field(min_length=1)
    state: CandidateState
    fingerprint: GenerationFingerprint
    candidate_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewable_body_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    document: PublishedDocument

    @model_validator(mode="after")
    def require_consistent_identity_and_state(self) -> GeneratedCandidate:
        """Prevent candidate metadata from contradicting its embedded document."""
        if (self.database, self.table) != (self.document.database, self.document.table):
            raise ValueError("candidate identity must match its embedded document")
        expected_status = (
            DocumentStatus.NEEDS_REVIEW
            if self.state is CandidateState.REVIEW
            else DocumentStatus.APPROVED
        )
        if self.document.document_status is not expected_status:
            raise ValueError("candidate state must match embedded document status")
        return self
