"""Tests for auditable candidate generation and status-only promotion."""

from dataclasses import replace
from pathlib import Path

import pytest

from metadata_pipeline.adapters.generator.deterministic import DeterministicDocumentGenerator
from metadata_pipeline.application.candidate_state import (
    CandidateStateError,
    create_candidate,
    promote_candidate,
    validate_candidate,
)
from metadata_pipeline.domain.candidate import CandidateState, GeneratedCandidate
from metadata_pipeline.domain.review import DocumentStatus
from metadata_pipeline.io.candidate_json import load_candidate, write_candidate
from metadata_pipeline.io.published_markdown import render_published_document
from metadata_pipeline.ports.document_generator import PublicationContext

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "contracts/metadata_contract.yml"
GUIDELINE = ROOT / "guidelines/llm_transformation_guideline.md"


def _candidate_context(context: PublicationContext) -> PublicationContext:
    review = context.review.model_copy(
        update={"owner": "commerce-owner", "reviewer": "analytics-reviewer"}
    )
    return replace(context, review=review)


def _candidate(context: PublicationContext) -> tuple[GeneratedCandidate, PublicationContext]:
    assigned = _candidate_context(context)
    document = DeterministicDocumentGenerator().generate(assigned)
    return create_candidate(document, assigned.review, CONTRACT, GUIDELINE), assigned


def _reviewable_body(document: object) -> str:
    rendered = render_published_document(document)  # type: ignore[arg-type]
    return "## Summary\n" + rendered.split("## Summary\n", maxsplit=1)[1]


def test_candidate_fingerprint_ignores_status_only_change(
    publication_context: PublicationContext,
) -> None:
    candidate, context = _candidate(publication_context)
    approved = context.review.model_copy(update={"document_status": DocumentStatus.APPROVED})

    validate_candidate(candidate, approved, CONTRACT, GUIDELINE)


def test_promotion_keeps_reviewed_body_and_never_regenerates(
    publication_context: PublicationContext,
) -> None:
    candidate, context = _candidate(publication_context)
    approved = context.review.model_copy(update={"document_status": DocumentStatus.APPROVED})

    promoted = promote_candidate(candidate, approved, "b" * 40, CONTRACT, GUIDELINE)

    assert promoted.state is CandidateState.PROMOTED
    assert promoted.document.document_status is DocumentStatus.APPROVED
    assert promoted.document.index_eligible is True
    assert promoted.candidate_hash == candidate.candidate_hash
    assert promoted.reviewable_body_hash == candidate.reviewable_body_hash
    assert _reviewable_body(promoted.document) == _reviewable_body(candidate.document)
    assert "Preview only" not in render_published_document(promoted.document)


def test_business_change_makes_candidate_stale(
    publication_context: PublicationContext,
) -> None:
    candidate, context = _candidate(publication_context)
    changed = context.review.model_copy(
        update={
            "business": context.review.business.model_copy(
                update={"description": "A materially changed reviewer description."}
            )
        }
    )

    with pytest.raises(CandidateStateError, match="inputs changed") as error:
        validate_candidate(candidate, changed, CONTRACT, GUIDELINE)

    assert error.value.code == "stale_candidate"


def test_tampered_structured_document_is_rejected(
    publication_context: PublicationContext,
) -> None:
    candidate, context = _candidate(publication_context)
    changed_document = candidate.document.model_copy(update={"summary": "Tampered summary"})
    tampered = candidate.model_copy(update={"document": changed_document})

    with pytest.raises(CandidateStateError, match="candidate_hash") as error:
        validate_candidate(tampered, context.review, CONTRACT, GUIDELINE)

    assert error.value.code == "tampered_candidate"


def test_business_change_and_approval_cannot_skip_candidate_review(
    publication_context: PublicationContext,
) -> None:
    candidate, context = _candidate(publication_context)
    changed_business = context.review.business.model_copy(update={"grain": "One changed row"})
    unsafe_approval = context.review.model_copy(
        update={
            "business": changed_business,
            "document_status": DocumentStatus.APPROVED,
        }
    )

    with pytest.raises(CandidateStateError) as error:
        promote_candidate(candidate, unsafe_approval, "c" * 40, CONTRACT, GUIDELINE)

    assert error.value.code == "approval_without_reviewed_candidate"


def test_candidate_json_round_trip_is_idempotent(
    publication_context: PublicationContext,
    tmp_path: Path,
) -> None:
    candidate, _ = _candidate(publication_context)
    path = tmp_path / "orders.json"

    assert write_candidate(path, candidate) is True
    assert write_candidate(path, candidate) is False
    assert load_candidate(path) == candidate
