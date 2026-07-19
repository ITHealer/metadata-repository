"""Unit tests for deterministic published Markdown rendering."""

from pathlib import Path

from metadata_pipeline.domain.published import PublishedDocument
from metadata_pipeline.io.published_markdown import (
    render_published_document,
    write_published_document,
)


def test_renderer_emits_stable_front_matter_and_required_sections(
    published_document: PublishedDocument,
) -> None:
    rendered = render_published_document(published_document)
    assert rendered.startswith("---\ndocument_id: commerce_demo.orders\n")
    assert "document_status: needs_review" in rendered
    assert "index_eligible: false" in rendered
    assert "Preview only" in rendered
    headings = (
        "## Summary",
        "## Grain and purpose",
        "## Appropriate use",
        "## Inappropriate use",
        "## Columns",
        "## Relationships and join risks",
        "## Business rules",
        "## Time and unit semantics",
        "## Data quality and caveats",
        "## Security",
        "## Evidence",
    )
    positions = tuple(rendered.index(heading) for heading in headings)
    assert positions == tuple(sorted(positions))
    assert "## Security\n\nNot applicable" in rendered


def test_published_writer_skips_unchanged_bytes(
    tmp_path: Path,
    published_document: PublishedDocument,
) -> None:
    path = tmp_path / "orders.md"
    assert write_published_document(path, published_document) is True
    first = path.read_bytes()
    assert write_published_document(path, published_document) is False
    assert path.read_bytes() == first
