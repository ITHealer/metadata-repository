"""Versioned manifest contracts for deterministic retrieval indexing."""

from __future__ import annotations

from enum import Enum

from pydantic import Field, model_validator

from metadata_pipeline.domain.published import Chunk
from metadata_pipeline.domain.review import StrictModel


class IndexActionType(str, Enum):
    """Document-level actions derived from Git path changes."""

    DELETE = "delete"
    UPSERT = "upsert"


class IndexAction(StrictModel):
    """One auditable delete/upsert instruction for a published document."""

    action: IndexActionType
    document_id: str = Field(min_length=1)
    source_path: str = Field(min_length=1)


class IndexedDocument(StrictModel):
    """One approved document and its current, self-contained chunk version."""

    document_id: str = Field(min_length=1)
    schema_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_review_commit: str = Field(pattern=r"^[0-9a-f]{7,64}$")
    transformation_guideline_version: str = Field(min_length=1)
    chunks: tuple[Chunk, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_one_approved_document(self) -> IndexedDocument:
        expected_parent = f"{self.document_id}::document"
        if any(chunk.parent_document_id != expected_parent for chunk in self.chunks):
            raise ValueError("all manifest chunks must belong to document_id")
        if any(not chunk.index_eligible for chunk in self.chunks):
            raise ValueError("manifest cannot contain unapproved chunks")
        expected_version = (
            self.schema_hash,
            self.source_review_commit,
            self.transformation_guideline_version,
        )
        if any(
            (
                chunk.schema_hash,
                chunk.source_review_commit,
                chunk.transformation_guideline_version,
            )
            != expected_version
            for chunk in self.chunks
        ):
            raise ValueError("manifest chunk versions must match the document version")
        if len({chunk.chunk_id for chunk in self.chunks}) != len(self.chunks):
            raise ValueError("manifest chunk IDs must be unique per document")
        return self


class IndexManifest(StrictModel):
    """Complete deterministic snapshot used by the manifest index adapter."""

    format_version: str = "manifest-v1"
    source_commit: str = Field(pattern=r"^[0-9a-f]{7,64}$")
    documents: tuple[IndexedDocument, ...] = ()

    @model_validator(mode="after")
    def require_unique_sorted_documents(self) -> IndexManifest:
        ids = tuple(document.document_id for document in self.documents)
        if len(ids) != len(set(ids)):
            raise ValueError("manifest document IDs must be unique")
        if ids != tuple(sorted(ids)):
            raise ValueError("manifest documents must be sorted by document_id")
        return self
