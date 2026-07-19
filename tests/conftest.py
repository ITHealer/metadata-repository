"""Project-wide fixtures for approved index and retrieval scenarios."""

from pathlib import Path

import pytest

from metadata_pipeline.adapters.generator.deterministic import DeterministicDocumentGenerator
from metadata_pipeline.adapters.schema.tbls_json import TblsSchemaSource
from metadata_pipeline.application.build_chunks import build_chunks
from metadata_pipeline.domain.published import Chunk
from metadata_pipeline.domain.review import (
    DocumentStatus,
    Evidence,
    EvidenceStatus,
    ReviewDocument,
)
from metadata_pipeline.io.review_yaml import load_review_document
from metadata_pipeline.ports.document_generator import PublicationContext

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def approved_chunks() -> tuple[Chunk, ...]:
    """Build approved demo chunks in memory without changing reviewer source files."""
    schema_path = ROOT / "schema/raw/commerce_demo/schema.json"
    review_dir = ROOT / "metadata/review/commerce_demo"
    schema = TblsSchemaSource(schema_path).load()
    tables = {table.name: table for table in schema.tables}
    chunks: list[Chunk] = []
    for review_path in sorted(review_dir.glob("*.yml")):
        review = _approved(load_review_document(review_path))
        context = PublicationContext(
            schema=schema,
            table=tables[review.table],
            review=review,
            source_schema_path="schema/raw/commerce_demo/schema.json",
            source_review_path=f"metadata/review/commerce_demo/{review_path.name}",
            source_review_commit="e" * 40,
        )
        document = DeterministicDocumentGenerator().generate(context)
        chunks.extend(build_chunks(document))
    return tuple(sorted(chunks, key=lambda item: item.chunk_id))


def _approved(review: ReviewDocument) -> ReviewDocument:
    return review.model_copy(
        update={
            "owner": "commerce-data-owner",
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
