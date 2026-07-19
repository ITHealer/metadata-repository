"""Unit tests for the provider-free published document generator."""

import pytest

from metadata_pipeline.adapters.generator.deterministic import DeterministicDocumentGenerator
from metadata_pipeline.domain.published import GeneratorMode
from metadata_pipeline.domain.review import DocumentStatus
from metadata_pipeline.ports.document_generator import (
    DocumentGenerationError,
    DocumentGenerator,
    PublicationContext,
)


def _generate(generator: DocumentGenerator, context: PublicationContext) -> str:
    """Exercise structural conformance to the DocumentGenerator protocol."""
    return generator.generate(context).document_id


def test_deterministic_generator_merges_raw_and_review_facts(
    publication_context: PublicationContext,
) -> None:
    generator = DeterministicDocumentGenerator()
    document = generator.generate(publication_context)

    assert _generate(generator, publication_context) == "commerce_demo.orders"
    assert document.provenance.generator_mode is GeneratorMode.MOCK
    assert document.provenance.generator_model == "deterministic-v1"
    assert [column.name for column in document.columns] == sorted(
        publication_context.review.columns
    )
    total_amount = next(column for column in document.columns if column.name == "total_amount")
    assert total_amount.data_type == "Decimal(18, 2)"
    assert total_amount.unit == "VND"
    assert document.relationships[0].technical_definition
    assert document.relationships[0].virtual is True


def test_deterministic_generator_is_byte_stable(
    publication_context: PublicationContext,
) -> None:
    generator = DeterministicDocumentGenerator()
    first = generator.generate(publication_context).model_dump_json()
    second = generator.generate(publication_context).model_dump_json()
    assert first == second


def test_deterministic_generator_rejects_stale_hash(
    publication_context: PublicationContext,
) -> None:
    stale_review = publication_context.review.model_copy(update={"schema_hash": "0" * 64})
    stale_context = PublicationContext(
        schema=publication_context.schema,
        table=publication_context.table,
        review=stale_review,
        source_schema_path=publication_context.source_schema_path,
        source_review_path=publication_context.source_review_path,
        source_review_commit=publication_context.source_review_commit,
    )
    with pytest.raises(DocumentGenerationError, match="schema_hash is stale"):
        DeterministicDocumentGenerator().generate(stale_context)


def test_approved_review_produces_index_eligible_document(
    publication_context: PublicationContext,
) -> None:
    review = publication_context.review.model_copy(
        update={
            "owner": "commerce-data-owner",
            "reviewer": "analytics-reviewer",
            "document_status": DocumentStatus.APPROVED,
        }
    )
    context = PublicationContext(
        schema=publication_context.schema,
        table=publication_context.table,
        review=review,
        source_schema_path=publication_context.source_schema_path,
        source_review_path=publication_context.source_review_path,
        source_review_commit=publication_context.source_review_commit,
    )

    document = DeterministicDocumentGenerator().generate(context)

    assert document.document_status is DocumentStatus.APPROVED
    assert document.index_eligible is True
