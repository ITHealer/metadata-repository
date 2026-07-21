"""Shared unit-test fixtures for the published metadata vertical slice."""

from pathlib import Path

import pytest

from metadata_pipeline.adapters.generator.deterministic import DeterministicDocumentGenerator
from metadata_pipeline.adapters.schema.tbls_json import TblsSchemaSource
from metadata_pipeline.domain.published import PublishedDocument
from metadata_pipeline.domain.review import DocumentStatus
from metadata_pipeline.io.review_yaml import load_review_document
from metadata_pipeline.ports.document_generator import PublicationContext

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def publication_context() -> PublicationContext:
    """Return a validated orders context backed by committed demo inputs."""
    schema_path = ROOT / "catalog/commerce_demo/generated/raw/schema.json"
    review_path = ROOT / "catalog/commerce_demo/review/orders.yml"
    schema = TblsSchemaSource(schema_path).load()
    table = next(table for table in schema.tables if table.name == "orders")
    review = load_review_document(review_path).model_copy(
        update={"document_status": DocumentStatus.NEEDS_REVIEW}
    )
    return PublicationContext(
        schema=schema,
        table=table,
        review=review,
        source_schema_path="catalog/commerce_demo/generated/raw/schema.json",
        source_review_path="catalog/commerce_demo/review/orders.yml",
        source_review_commit="a" * 40,
    )


@pytest.fixture
def published_document(publication_context: PublicationContext) -> PublishedDocument:
    """Return the deterministic baseline for model invariant tests."""
    return DeterministicDocumentGenerator().generate(publication_context)
