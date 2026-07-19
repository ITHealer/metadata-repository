"""Contracts for deterministic golden-question retrieval evaluation."""

from __future__ import annotations

from pydantic import Field

from metadata_pipeline.domain.review import StrictModel


class GoldenQuestion(StrictModel):
    """One expected document and fact-preservation assertion."""

    question_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    expected_documents: tuple[str, ...] = Field(min_length=1)
    required_facts: tuple[str, ...] = Field(min_length=1)


class RetrievalHit(StrictModel):
    """One ranked lexical retrieval result."""

    rank: int = Field(ge=1)
    chunk_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    score: int = Field(ge=0)
    content: str = Field(min_length=1)


class QuestionResult(StrictModel):
    """Per-question document and required-fact outcome."""

    question_id: str = Field(min_length=1)
    document_found: bool
    missing_facts: tuple[str, ...] = ()
    hits: tuple[RetrievalHit, ...]


class RetrievalReport(StrictModel):
    """Stable report used as a CI quality gate and uploaded artifact."""

    total_questions: int = Field(ge=1)
    document_hits: int = Field(ge=0)
    top_k: int = Field(ge=1)
    document_hit_rate: float = Field(ge=0, le=1)
    passed: bool
    results: tuple[QuestionResult, ...]
