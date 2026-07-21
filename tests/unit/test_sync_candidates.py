"""Tests for loop-safe candidate synchronization orchestration."""

from collections.abc import Callable
from pathlib import Path
from shutil import copy2, copytree

from metadata_pipeline.adapters.generator.deterministic import DeterministicDocumentGenerator
from metadata_pipeline.application.sync_candidates import (
    CandidateSyncAction,
    CandidateSyncBatch,
    GeneratorIdentity,
    prepare_candidate_sync,
    write_candidate_sync,
)
from metadata_pipeline.domain.published import PublishedDocument
from metadata_pipeline.domain.review import DocumentStatus, Evidence, EvidenceStatus, ReviewDocument
from metadata_pipeline.io.candidate_json import load_candidate
from metadata_pipeline.io.published_markdown import render_published_document
from metadata_pipeline.io.review_yaml import load_review_document, write_review_document
from metadata_pipeline.ports.document_generator import DocumentGenerator

ROOT = Path(__file__).resolve().parents[2]


def _workspace(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path, Path]:
    schema = tmp_path / "raw/schema.json"
    schema.parent.mkdir()
    copy2(ROOT / "tests/fixtures/commerce_demo/schema.json", schema)
    reviews = tmp_path / "review"
    copytree(ROOT / "tests/fixtures/commerce_demo/review", reviews)
    orders_path = reviews / "orders.yml"
    orders = load_review_document(orders_path).model_copy(
        update={"document_status": DocumentStatus.NEEDS_REVIEW}
    )
    write_review_document(orders_path, orders)
    contract = tmp_path / "metadata_contract.yml"
    guideline = tmp_path / "guideline.md"
    copy2(ROOT / "contracts/metadata_contract.yml", contract)
    copy2(ROOT / "guidelines/llm_transformation_guideline.md", guideline)
    return schema, reviews, contract, guideline, tmp_path / "structured", tmp_path / "published"


def _sync(
    workspace: tuple[Path, Path, Path, Path, Path, Path],
    generator_factory: Callable[[], DocumentGenerator],
) -> CandidateSyncBatch:
    schema, reviews, contract, guideline, structured, published = workspace
    return prepare_candidate_sync(
        schema_path=schema,
        review_dir=reviews,
        contract_path=contract,
        guideline_path=guideline,
        structured_dir=structured,
        published_dir=published,
        source_review_commit="a" * 40,
        selected_tables=("orders",),
        identity_factory=lambda: GeneratorIdentity("deterministic-v1", "deterministic-v1"),
        generator_factory=generator_factory,
    )


def test_generates_then_validates_same_candidate_without_generator(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    calls = 0

    def generator() -> DocumentGenerator:
        nonlocal calls
        calls += 1
        return DeterministicDocumentGenerator()

    generated = _sync(workspace, generator)
    first_results = write_candidate_sync(generated)
    validated = _sync(workspace, lambda: (_ for _ in ()).throw(AssertionError("unexpected")))
    second_results = write_candidate_sync(validated)

    assert calls == 1
    assert first_results[0].action is CandidateSyncAction.GENERATED
    assert first_results[0].candidate_changed is True
    assert first_results[0].markdown_changed is True
    assert second_results[0].action is CandidateSyncAction.VALIDATED
    assert second_results[0].candidate_changed is False
    assert second_results[0].markdown_changed is False


def test_approval_promotes_existing_candidate_without_generator(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _, reviews, _, _, structured, published = workspace
    review_path = reviews / "orders.yml"
    review_ready = _approved(load_review_document(review_path)).model_copy(
        update={"document_status": DocumentStatus.NEEDS_REVIEW}
    )
    write_review_document(review_path, review_ready)
    generated = _sync(workspace, lambda: DeterministicDocumentGenerator())
    write_candidate_sync(generated)
    before = load_candidate(structured / "orders.json")
    review = review_ready.model_copy(update={"document_status": DocumentStatus.APPROVED})
    write_review_document(review_path, review)

    promoted = _sync(workspace, lambda: (_ for _ in ()).throw(AssertionError("LLM called")))
    result = write_candidate_sync(promoted)[0]
    after = load_candidate(structured / "orders.json")

    assert result.action is CandidateSyncAction.PROMOTED
    assert after.document.index_eligible is True
    assert after.candidate_hash == before.candidate_hash
    assert _body(after.document) == _body(before.document)
    assert "Preview only" not in (published / "orders.md").read_text(encoding="utf-8")


def _approved(review: ReviewDocument) -> ReviewDocument:
    return review.model_copy(
        update={
            "owner": "commerce-owner",
            "reviewer": "analytics-reviewer",
            "document_status": DocumentStatus.APPROVED,
            "business": review.business.model_copy(
                update={"evidence": _confirmed(review.business.evidence)}
            ),
            "columns": {
                name: column.model_copy(update={"evidence": _confirmed(column.evidence)})
                for name, column in review.columns.items()
            },
            "relationships": tuple(
                relationship.model_copy(update={"evidence": _confirmed(relationship.evidence)})
                for relationship in review.relationships
            ),
            "business_rules": tuple(
                rule.model_copy(update={"evidence": _confirmed(rule.evidence)})
                for rule in review.business_rules
            ),
        }
    )


def _confirmed(evidence: tuple[Evidence, ...]) -> tuple[Evidence, ...]:
    return tuple(item.model_copy(update={"status": EvidenceStatus.CONFIRMED}) for item in evidence)


def _body(document: PublishedDocument) -> str:
    markdown = render_published_document(document)
    return "## Summary\n" + markdown.split("## Summary\n", maxsplit=1)[1]
