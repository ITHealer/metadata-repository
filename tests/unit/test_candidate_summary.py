"""Tests for zero-tool reviewer summaries."""

from pathlib import Path

from metadata_pipeline.adapters.generator.deterministic import DeterministicDocumentGenerator
from metadata_pipeline.adapters.schema.tbls_json import TblsSchemaSource
from metadata_pipeline.application.candidate_state import create_candidate
from metadata_pipeline.application.candidate_summary import render_candidate_summary
from metadata_pipeline.domain.review import DocumentStatus
from metadata_pipeline.io.candidate_json import write_candidate
from metadata_pipeline.io.review_yaml import load_review_document, write_review_document
from metadata_pipeline.ports.document_generator import PublicationContext

ROOT = Path(__file__).resolve().parents[2]


def test_summary_links_reviewer_input_preview_and_candidate_hash(tmp_path: Path) -> None:
    review_dir = tmp_path / "catalog/commerce_demo/review"
    structured_dir = tmp_path / "catalog/commerce_demo/generated/structured"
    published_dir = tmp_path / "catalog/commerce_demo/generated/published"
    review_path = review_dir / "orders.yml"
    review = load_review_document(
        ROOT / "tests/fixtures/commerce_demo/review/orders.yml"
    ).model_copy(update={"document_status": DocumentStatus.NEEDS_REVIEW})
    write_review_document(review_path, review)
    schema = TblsSchemaSource(ROOT / "tests/fixtures/commerce_demo/schema.json").load()
    table = next(table for table in schema.tables if table.name == "orders")
    context = PublicationContext(
        schema=schema,
        table=table,
        review=review,
        source_schema_path="catalog/commerce_demo/generated/raw/schema.json",
        source_review_path="catalog/commerce_demo/review/orders.yml",
        source_review_commit="a" * 40,
    )
    document = DeterministicDocumentGenerator().generate(context)
    candidate = create_candidate(
        document,
        review,
        ROOT / "contracts/metadata_contract.yml",
        ROOT / "guidelines/llm_transformation_guideline.md",
    )
    write_candidate(structured_dir / "orders.json", candidate)
    rendered = render_candidate_summary(
        repository_root=tmp_path,
        database="commerce_demo",
        review_dir=review_dir,
        structured_dir=structured_dir,
        published_dir=published_dir,
        repository_url="https://github.com/ITHealer/metadata-repository/blob/abc123",
    )

    assert "### Metadata candidates: `commerce_demo`" in rendered
    expected_state = f"| `orders` | `{review.document_status.value}` | `{candidate.state.value}` |"
    assert expected_state in rendered
    assert "blob/abc123/catalog/commerce_demo/review/orders.yml" in rendered
    assert "blob/abc123/catalog/commerce_demo/generated/published/orders.md" in rendered
    assert "edit only YAML" in rendered
