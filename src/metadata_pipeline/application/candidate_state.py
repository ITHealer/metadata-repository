"""Generate, validate, and safely promote persistent metadata candidates."""

from __future__ import annotations

from pathlib import Path

from metadata_pipeline.domain.candidate import (
    CandidateState,
    GeneratedCandidate,
    GenerationFingerprint,
)
from metadata_pipeline.domain.hashing import bytes_sha256, canonical_sha256
from metadata_pipeline.domain.published import PublishedDocument
from metadata_pipeline.domain.review import DocumentStatus, ReviewDocument
from metadata_pipeline.io.published_markdown import render_published_document


class CandidateStateError(ValueError):
    """Actionable state-machine failure exposed to CI and reviewers."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def create_candidate(
    document: PublishedDocument,
    review: ReviewDocument,
    contract_path: Path,
    guideline_path: Path,
) -> GeneratedCandidate:
    """Freeze a generated needs-review document and all of its material inputs."""
    if review.document_status is not DocumentStatus.NEEDS_REVIEW:
        raise CandidateStateError(
            "candidate_requires_review",
            "new candidates can be generated only while document_status is needs_review",
        )
    if document.document_status is not DocumentStatus.NEEDS_REVIEW:
        raise CandidateStateError(
            "candidate_status_mismatch",
            "generated document status does not match reviewer status",
        )
    fingerprint = build_fingerprint(
        review,
        contract_path,
        guideline_path,
        document.provenance.generator_model,
        document.provenance.prompt_version,
    )
    return GeneratedCandidate(
        database=document.database,
        table=document.table,
        state=CandidateState.REVIEW,
        fingerprint=fingerprint,
        candidate_hash=_candidate_hash(document),
        reviewable_body_hash=_reviewable_body_hash(document),
        document=document,
    )


def validate_candidate(
    candidate: GeneratedCandidate,
    review: ReviewDocument,
    contract_path: Path,
    guideline_path: Path,
) -> None:
    """Reject stale, tampered, or identity-mismatched candidate artifacts."""
    if (candidate.database, candidate.table) != (review.database, review.table):
        raise CandidateStateError(
            "candidate_identity_mismatch", "candidate database/table does not match reviewer YAML"
        )
    expected_fingerprint = build_fingerprint(
        review,
        contract_path,
        guideline_path,
        candidate.document.provenance.generator_model,
        candidate.document.provenance.prompt_version,
    )
    if candidate.fingerprint != expected_fingerprint:
        raise CandidateStateError(
            "stale_candidate",
            "candidate inputs changed after generation; generate and review a new candidate",
        )
    validate_candidate_integrity(candidate)


def validate_candidate_integrity(candidate: GeneratedCandidate) -> None:
    """Validate persisted structured/Markdown hashes without loading source inputs."""
    if candidate.candidate_hash != _candidate_hash(candidate.document):
        raise CandidateStateError(
            "tampered_candidate", "candidate structured document does not match candidate_hash"
        )
    if candidate.reviewable_body_hash != _reviewable_body_hash(candidate.document):
        raise CandidateStateError(
            "tampered_candidate", "candidate Markdown body does not match reviewable_body_hash"
        )


def promote_candidate(
    candidate: GeneratedCandidate,
    approved_review: ReviewDocument,
    source_review_commit: str,
    contract_path: Path,
    guideline_path: Path,
) -> GeneratedCandidate:
    """Promote the exact reviewed narrative without any generator or network dependency."""
    if candidate.state is not CandidateState.REVIEW:
        raise CandidateStateError(
            "invalid_candidate_state", "only a review-state candidate can be promoted"
        )
    if approved_review.document_status is not DocumentStatus.APPROVED:
        raise CandidateStateError(
            "approval_required", "reviewer YAML must have document_status approved"
        )
    try:
        validate_candidate(candidate, approved_review, contract_path, guideline_path)
    except CandidateStateError as error:
        if error.code == "stale_candidate":
            raise CandidateStateError(
                "approval_without_reviewed_candidate",
                "business inputs changed before approval; generate and review a new candidate",
            ) from error
        raise
    provenance = candidate.document.provenance.model_copy(
        update={"source_review_commit": source_review_commit}
    )
    approved_document = PublishedDocument.model_validate(
        candidate.document.model_copy(
            update={
                "document_status": DocumentStatus.APPROVED,
                "index_eligible": True,
                "provenance": provenance,
            }
        ).model_dump()
    )
    if _reviewable_body_hash(approved_document) != candidate.reviewable_body_hash:
        raise CandidateStateError(
            "approval_changed_narrative", "approval must not change the reviewed Markdown body"
        )
    promoted = candidate.model_copy(
        update={"state": CandidateState.PROMOTED, "document": approved_document}
    )
    return GeneratedCandidate.model_validate(promoted.model_dump())


def build_fingerprint(
    review: ReviewDocument,
    contract_path: Path,
    guideline_path: Path,
    generator_model: str,
    prompt_version: str,
) -> GenerationFingerprint:
    """Hash status-independent reviewer content plus every generation contract input."""
    review_payload = review.model_dump(mode="json")
    review_payload.pop("document_status")
    components = {
        "schema_hash": review.schema_hash,
        "review_content_hash": canonical_sha256(review_payload),
        "contract_hash": _file_hash(contract_path),
        "guideline_hash": _file_hash(guideline_path),
        "generator_model": generator_model,
        "prompt_version": prompt_version,
    }
    return GenerationFingerprint(**components, input_hash=canonical_sha256(components))


def _candidate_hash(document: PublishedDocument) -> str:
    payload = document.model_dump(mode="json")
    payload.pop("document_status")
    payload.pop("index_eligible")
    provenance = payload["provenance"]
    if isinstance(provenance, dict):
        provenance.pop("source_review_commit")
    return canonical_sha256(payload)


def _reviewable_body_hash(document: PublishedDocument) -> str:
    markdown = render_published_document(document)
    marker = "## Summary\n"
    try:
        body = marker + markdown.split(marker, maxsplit=1)[1]
    except IndexError as error:
        raise CandidateStateError(
            "invalid_candidate_markdown", "rendered candidate has no Summary section"
        ) from error
    return bytes_sha256(body.encode("utf-8"))


def _file_hash(path: Path) -> str:
    try:
        return bytes_sha256(path.read_bytes())
    except OSError as error:
        raise CandidateStateError(
            "missing_generation_input", f"unable to hash {path}: {error}"
        ) from error
