"""Evaluate lexical retrieval against version-controlled golden questions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

import yaml
from pydantic import TypeAdapter, ValidationError

from metadata_pipeline.adapters.index.lexical import LexicalRetriever
from metadata_pipeline.domain.published import Chunk
from metadata_pipeline.domain.retrieval import (
    GoldenQuestion,
    QuestionResult,
    RetrievalHit,
    RetrievalReport,
)
from metadata_pipeline.io.atomic_text import write_text_if_changed

_QUESTION_LIST = TypeAdapter(tuple[GoldenQuestion, ...])


class Retriever(Protocol):
    """Minimal search boundary shared by lexical and live vector evaluation."""

    def search(self, question: str, top_k: int = 3) -> tuple[RetrievalHit, ...]:
        """Return ranked retrieval hits."""
        ...


def load_golden_questions(path: Path) -> tuple[GoldenQuestion, ...]:
    """Load strict YAML questions with unique IDs."""
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        questions = _QUESTION_LIST.validate_python(payload)
    except (OSError, yaml.YAMLError, ValidationError) as error:
        raise ValueError(f"{path}: invalid golden questions: {error}") from error
    ids = tuple(question.question_id for question in questions)
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path}: golden question IDs must be unique")
    return questions


def evaluate_retrieval(
    chunks: tuple[Chunk, ...],
    questions: tuple[GoldenQuestion, ...],
    *,
    top_k: int = 3,
    minimum_document_hit_rate: float = 0.9,
) -> RetrievalReport:
    """Require expected top-k documents and co-located facts for every question."""
    if not questions:
        raise ValueError("at least one golden question is required")
    if top_k < 1:
        raise ValueError("top_k must be at least 1")
    if not 0 <= minimum_document_hit_rate <= 1:
        raise ValueError("minimum_document_hit_rate must be between 0 and 1")
    return evaluate_retriever(
        LexicalRetriever(chunks),
        questions,
        top_k=top_k,
        minimum_document_hit_rate=minimum_document_hit_rate,
    )


def evaluate_retriever(
    retriever: Retriever,
    questions: tuple[GoldenQuestion, ...],
    *,
    top_k: int = 3,
    minimum_document_hit_rate: float = 0.9,
) -> RetrievalReport:
    """Apply the same golden-question gate to any retrieval adapter."""
    if not questions:
        raise ValueError("at least one golden question is required")
    if top_k < 1:
        raise ValueError("top_k must be at least 1")
    if not 0 <= minimum_document_hit_rate <= 1:
        raise ValueError("minimum_document_hit_rate must be between 0 and 1")
    results: list[QuestionResult] = []
    document_hits = 0
    for question in questions:
        hits = retriever.search(question.question, top_k=top_k)
        found = any(hit.document_id in question.expected_documents for hit in hits)
        document_hits += int(found)
        combined = "\n".join(hit.content for hit in hits).lower()
        missing = tuple(fact for fact in question.required_facts if fact.lower() not in combined)
        results.append(
            QuestionResult(
                question_id=question.question_id,
                document_found=found,
                missing_facts=missing,
                hits=hits,
            )
        )
    hit_rate = document_hits / len(questions)
    passed = hit_rate >= minimum_document_hit_rate and all(
        not result.missing_facts for result in results
    )
    return RetrievalReport(
        total_questions=len(questions),
        document_hits=document_hits,
        top_k=top_k,
        document_hit_rate=hit_rate,
        passed=passed,
        results=tuple(results),
    )


def write_retrieval_report(path: Path, report: RetrievalReport) -> bool:
    """Write stable JSON for CI inspection."""
    content = json.dumps(
        report.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    return write_text_if_changed(path, content + "\n")
