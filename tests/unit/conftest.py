"""Shared unit-test fixtures for the published metadata vertical slice."""

from pathlib import Path

import pytest

from metadata_pipeline.adapters.generator.deterministic import DeterministicDocumentGenerator
from metadata_pipeline.adapters.schema.tbls_json import TblsSchemaSource
from metadata_pipeline.domain.published import PublishedDocument
from metadata_pipeline.io.review_yaml import load_review_document
from metadata_pipeline.ports.document_generator import PublicationContext

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def publication_context() -> PublicationContext:
    """Return a validated orders context backed by committed demo inputs."""
    schema_path = ROOT / "schema/raw/commerce_demo/schema.json"
    review_path = ROOT / "metadata/review/commerce_demo/orders.yml"
    schema = TblsSchemaSource(schema_path).load()
    table = next(table for table in schema.tables if table.name == "orders")
    return PublicationContext(
        schema=schema,
        table=table,
        review=load_review_document(review_path),
        source_schema_path="schema/raw/commerce_demo/schema.json",
        source_review_path="metadata/review/commerce_demo/orders.yml",
        source_review_commit="a" * 40,
    )


@pytest.fixture
def published_document(publication_context: PublicationContext) -> PublishedDocument:
    """Return the deterministic baseline for model invariant tests."""
    return DeterministicDocumentGenerator().generate(publication_context)
