"""Versioned manifest contracts for deterministic retrieval indexing."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import Field, model_validator

from metadata_pipeline.domain.hashing import canonical_sha256
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


class ChunkActionType(str, Enum):
    """Mutation required to reconcile one desired chunk."""

    DELETE = "delete"
    SKIP = "skip"
    UPSERT = "upsert"


class ChunkActionReason(str, Enum):
    """Why a chunk mutation or no-op was selected."""

    CREATED = "created"
    REMOVED = "removed"
    UNCHANGED = "unchanged"
    UPDATED = "updated"


class ChunkAction(StrictModel):
    """Deterministic old/new body-hash transition for one chunk ID."""

    operation: ChunkActionType
    reason: ChunkActionReason
    chunk_id: str = Field(min_length=1)
    old_hash: Optional[str] = Field(default=None, pattern=r"^[0-9a-f]{64}$")  # noqa: UP007
    new_hash: Optional[str] = Field(default=None, pattern=r"^[0-9a-f]{64}$")  # noqa: UP007


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

    format_version: str = "manifest-v2"
    source_commit: str = Field(pattern=r"^[0-9a-f]{7,64}$")
    documents: tuple[IndexedDocument, ...] = ()
    manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @classmethod
    def create(
        cls,
        *,
        source_commit: str,
        documents: tuple[IndexedDocument, ...] = (),
    ) -> IndexManifest:
        """Build a manifest whose hash excludes only the hash field itself."""
        payload = {
            "format_version": "manifest-v2",
            "source_commit": source_commit,
            "documents": [document.model_dump(mode="json") for document in documents],
        }
        return cls(
            source_commit=source_commit,
            documents=documents,
            manifest_hash=canonical_sha256(payload),
        )

    @model_validator(mode="after")
    def require_unique_sorted_documents(self) -> IndexManifest:
        ids = tuple(document.document_id for document in self.documents)
        if len(ids) != len(set(ids)):
            raise ValueError("manifest document IDs must be unique")
        if ids != tuple(sorted(ids)):
            raise ValueError("manifest documents must be sorted by document_id")
        expected_hash = canonical_sha256(self.model_dump(mode="json", exclude={"manifest_hash"}))
        if self.manifest_hash != expected_hash:
            raise ValueError("manifest_hash must match the canonical manifest payload")
        return self
