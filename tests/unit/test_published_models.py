"""Unit tests for published document and semantic chunk invariants."""

import pytest
from pydantic import ValidationError

from metadata_pipeline.domain.published import Chunk, ChunkType, PublishedDocument
from metadata_pipeline.domain.review import DocumentStatus


def test_published_document_is_strict_and_needs_review_is_not_indexable(
    published_document: PublishedDocument,
) -> None:
    assert published_document.document_id == "commerce_demo.orders"
    assert published_document.document_status is DocumentStatus.NEEDS_REVIEW
    assert published_document.index_eligible is False

    payload = published_document.model_dump()
    payload["unexpected"] = "not allowed"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PublishedDocument.model_validate(payload)


def test_published_document_rejects_inconsistent_index_eligibility(
    published_document: PublishedDocument,
) -> None:
    payload = published_document.model_dump()
    payload["index_eligible"] = True
    with pytest.raises(ValidationError, match="true only for approved"):
        PublishedDocument.model_validate(payload)


def test_chunk_requires_stable_identity_and_status(
    published_document: PublishedDocument,
) -> None:
    chunk = Chunk(
        chunk_id="commerce_demo.orders::table_overview::summary",
        parent_document_id="commerce_demo.orders::document",
        semantic_key="summary",
        chunk_type=ChunkType.TABLE_OVERVIEW,
        database=published_document.database,
        table=published_document.table,
        qualified_name=published_document.qualified_name,
        document_status=published_document.document_status,
        index_eligible=False,
        schema_hash=published_document.schema_hash,
        contract_version=published_document.contract_version,
        review_guideline_version=published_document.review_guideline_version,
        transformation_guideline_version=published_document.transformation_guideline_version,
        source_review_path=published_document.provenance.source_review_path,
        source_review_commit=published_document.provenance.source_review_commit,
        content=published_document.summary,
        evidence=published_document.business_evidence,
    )
    assert chunk.parent_document_id == published_document.document_id + "::document"

    invalid = chunk.model_dump()
    invalid["chunk_id"] = "unstable-id"
    with pytest.raises(ValidationError, match="chunk_id must match"):
        Chunk.model_validate(invalid)
