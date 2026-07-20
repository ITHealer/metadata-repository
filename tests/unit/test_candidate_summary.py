"""Tests for zero-tool reviewer summaries."""

from pathlib import Path

from metadata_pipeline.application.candidate_summary import render_candidate_summary

ROOT = Path(__file__).resolve().parents[2]


def test_summary_links_reviewer_input_preview_and_candidate_hash() -> None:
    rendered = render_candidate_summary(
        repository_root=ROOT,
        database="commerce_demo",
        review_dir=ROOT / "catalog/commerce_demo/review",
        structured_dir=ROOT / "catalog/commerce_demo/generated/structured",
        published_dir=ROOT / "catalog/commerce_demo/generated/published",
        repository_url="https://github.com/ITHealer/metadata-repository/blob/abc123",
    )

    assert "### Metadata candidates: `commerce_demo`" in rendered
    assert "| `orders` | `needs_review` | `review` |" in rendered
    assert "blob/abc123/catalog/commerce_demo/review/orders.yml" in rendered
    assert "blob/abc123/catalog/commerce_demo/generated/published/orders.md" in rendered
    assert "edit only YAML" in rendered
