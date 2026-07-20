"""All-or-nothing orchestration for candidate generation, validation, and promotion."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from metadata_pipeline.application.candidate_state import (
    CandidateStateError,
    create_candidate,
    promote_candidate,
    validate_candidate,
)
from metadata_pipeline.application.publish_metadata import (
    prepare_publication,
)
from metadata_pipeline.application.review_contract import validate_review_directory
from metadata_pipeline.domain.candidate import CandidateState, GeneratedCandidate
from metadata_pipeline.domain.review import DocumentStatus, ReviewDocument
from metadata_pipeline.io.candidate_json import (
    CandidateFileError,
    load_candidate,
    write_candidate,
)
from metadata_pipeline.io.published_markdown import write_published_document
from metadata_pipeline.io.review_yaml import ReviewFileError, load_review_document
from metadata_pipeline.ports.document_generator import DocumentGenerator
from metadata_pipeline.validation.review import IssueSeverity


class CandidateSyncAction(str, Enum):
    """Observable decision for one table in a candidate sync."""

    GENERATED = "generated"
    VALIDATED = "validated"
    PROMOTED = "promoted"


@dataclass(frozen=True)
class GeneratorIdentity:
    """Configured model identity used to decide whether a candidate is current."""

    model: str
    prompt_version: str


@dataclass(frozen=True)
class CandidateSyncItem:
    """One fully prepared candidate and its two generated output paths."""

    table: str
    candidate_path: Path
    markdown_path: Path
    candidate: GeneratedCandidate
    action: CandidateSyncAction


@dataclass(frozen=True)
class CandidateSyncBatch:
    """Preflighted candidate writes for one database."""

    items: tuple[CandidateSyncItem, ...]


@dataclass(frozen=True)
class CandidateSyncResult:
    """Filesystem outcome for one candidate/Markdown pair."""

    table: str
    action: CandidateSyncAction
    candidate_changed: bool
    markdown_changed: bool


def prepare_candidate_sync(
    *,
    schema_path: Path,
    review_dir: Path,
    contract_path: Path,
    guideline_path: Path,
    structured_dir: Path,
    published_dir: Path,
    source_review_commit: str,
    selected_tables: tuple[str, ...],
    identity_factory: Callable[[], GeneratorIdentity] | None,
    generator_factory: Callable[[], DocumentGenerator] | None,
) -> CandidateSyncBatch:
    """Plan every state transition before writing or creating an LLM client."""
    issues = validate_review_directory(schema_path, review_dir, contract_path)
    blockers = tuple(
        issue
        for issue in issues
        if issue.severity is IssueSeverity.ERROR or issue.code == "conflicting_evidence"
    )
    if blockers:
        details = "; ".join(f"{issue.code}: {issue.message}" for issue in blockers)
        raise CandidateStateError("candidate_preflight_failed", details)
    reviews = _load_selected_reviews(review_dir, selected_tables)
    items: dict[str, CandidateSyncItem] = {}
    pending_generation: list[str] = []
    identity: GeneratorIdentity | None = None

    for _review_path, review in reviews:
        candidate_path = structured_dir / f"{review.table}.json"
        markdown_path = published_dir / f"{review.table}.md"
        try:
            candidate = load_candidate(candidate_path)
        except CandidateFileError:
            candidate = None

        if review.document_status is DocumentStatus.APPROVED:
            if candidate is None:
                raise CandidateStateError(
                    "approval_without_reviewed_candidate",
                    f"{review.table}: approved reviewer YAML has no generated candidate",
                )
            if candidate.state is CandidateState.PROMOTED:
                validate_candidate(candidate, review, contract_path, guideline_path)
                promoted = candidate
            else:
                promoted = promote_candidate(
                    candidate,
                    review,
                    source_review_commit,
                    contract_path,
                    guideline_path,
                )
            items[review.table] = CandidateSyncItem(
                review.table,
                candidate_path,
                markdown_path,
                promoted,
                (
                    CandidateSyncAction.VALIDATED
                    if candidate.state is CandidateState.PROMOTED
                    else CandidateSyncAction.PROMOTED
                ),
            )
            continue

        if candidate is not None and candidate.state is CandidateState.REVIEW:
            try:
                validate_candidate(candidate, review, contract_path, guideline_path)
                if identity is None and identity_factory is not None:
                    identity = identity_factory()
                if identity is not None and (
                    candidate.fingerprint.generator_model != identity.model
                    or candidate.fingerprint.prompt_version != identity.prompt_version
                ):
                    raise CandidateStateError(
                        "stale_candidate", "configured model or prompt version changed"
                    )
            except CandidateStateError as error:
                if error.code not in {"stale_candidate"}:
                    raise
            else:
                items[review.table] = CandidateSyncItem(
                    review.table,
                    candidate_path,
                    markdown_path,
                    candidate,
                    CandidateSyncAction.VALIDATED,
                )
                continue
        pending_generation.append(review.table)

    if pending_generation:
        if generator_factory is None:
            tables = ", ".join(sorted(pending_generation))
            raise CandidateStateError(
                "generation_required",
                f"candidate generation is required for: {tables}",
            )
        generator = generator_factory()
        publication = prepare_publication(
            schema_path,
            review_dir,
            contract_path,
            published_dir,
            source_review_commit,
            generator,
            tuple(sorted(pending_generation)),
        )
        for prepared in publication.items:
            candidate = create_candidate(
                prepared.document,
                prepared.context.review,
                contract_path,
                guideline_path,
            )
            items[prepared.document.table] = CandidateSyncItem(
                prepared.document.table,
                structured_dir / f"{prepared.document.table}.json",
                prepared.output_path,
                candidate,
                CandidateSyncAction.GENERATED,
            )

    return CandidateSyncBatch(tuple(items[table] for table in sorted(items)))


def write_candidate_sync(batch: CandidateSyncBatch) -> tuple[CandidateSyncResult, ...]:
    """Persist a fully preflighted sync using atomic per-file writers."""
    results = []
    for item in batch.items:
        candidate_changed = write_candidate(item.candidate_path, item.candidate)
        markdown_changed = write_published_document(item.markdown_path, item.candidate.document)
        results.append(
            CandidateSyncResult(
                item.table,
                item.action,
                candidate_changed,
                markdown_changed,
            )
        )
    return tuple(results)


def _load_selected_reviews(
    review_dir: Path,
    selected_tables: tuple[str, ...],
) -> tuple[tuple[Path, ReviewDocument], ...]:
    paths = sorted((*review_dir.glob("*.yml"), *review_dir.glob("*.yaml")))
    reviews = []
    try:
        reviews = [(path, load_review_document(path)) for path in paths]
    except ReviewFileError as error:
        raise CandidateStateError("invalid_review_document", str(error)) from error
    available = {review.table for _, review in reviews}
    requested = set(selected_tables)
    missing = sorted(requested - available)
    if missing:
        raise CandidateStateError(
            "unknown_selected_table", f"reviewer YAML not found for: {', '.join(missing)}"
        )
    if requested:
        reviews = [(path, review) for path, review in reviews if review.table in requested]
    if not reviews:
        raise CandidateStateError("missing_review_files", f"no reviewer YAML found in {review_dir}")
    return tuple(reviews)
