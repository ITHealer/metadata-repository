"""Provider-neutral vector collection boundary."""

from __future__ import annotations

from typing import Protocol

from pydantic import Field

from metadata_pipeline.domain.review import StrictModel


class VectorIndexError(RuntimeError):
    """Raised when collection state cannot be safely read or changed."""


class VectorCollectionInfo(StrictModel):
    """Vector-space contract that must match before apply."""

    dimension: int = Field(gt=0)
    distance: str = Field(min_length=1)


class VectorChunkState(StrictModel):
    """Managed point identity used for idempotent reconciliation."""

    point_id: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    body_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class VectorPoint(StrictModel):
    """One vector and filterable payload ready for an upsert."""

    point_id: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    body_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    vector: tuple[float, ...] = Field(min_length=1)
    payload: dict[str, object]


class VectorSearchHit(StrictModel):
    """Provider-independent semantic retrieval result."""

    chunk_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    content: str = Field(min_length=1)
    score: float


class VectorIndex(Protocol):
    """Read and mutate only points managed by this metadata pipeline."""

    def point_id_for_chunk(self, chunk_id: str) -> str:
        """Map a stable business ID to the provider's accepted point ID."""
        ...

    def collection_info(self) -> VectorCollectionInfo | None:
        """Return the existing collection contract, or None when absent."""
        ...

    def create_collection(self, dimension: int, distance: str) -> None:
        """Create an absent collection without deleting existing data."""
        ...

    def list_chunk_states(self) -> tuple[VectorChunkState, ...]:
        """List all points in the managed namespace."""
        ...

    def upsert(self, points: tuple[VectorPoint, ...]) -> None:
        """Insert or replace a deterministic batch."""
        ...

    def delete(self, point_ids: tuple[str, ...]) -> None:
        """Delete exact managed point IDs."""
        ...

    def search(self, vector: tuple[float, ...], limit: int) -> tuple[VectorSearchHit, ...]:
        """Search only the managed namespace."""
        ...
