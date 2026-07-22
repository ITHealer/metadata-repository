"""Explicit, non-destructive vector collection bootstrap."""

from __future__ import annotations

from enum import Enum

from metadata_pipeline.io.index_settings import IndexSettings
from metadata_pipeline.ports.vector_index import VectorIndex, VectorIndexError


class BootstrapOutcome(str, Enum):
    """Observable collection bootstrap result."""

    CREATED = "created"
    EXISTS = "exists"


def bootstrap_vector_index(settings: IndexSettings, index: VectorIndex) -> BootstrapOutcome:
    """Create an absent cosine collection and reject incompatible existing state."""
    info = index.collection_info()
    if info is None:
        index.create_collection(settings.embedding_dimension, "cosine")
        return BootstrapOutcome.CREATED
    if info.dimension != settings.embedding_dimension or info.distance.lower() != "cosine":
        raise VectorIndexError(
            "existing collection does not match configured embedding dimension and cosine distance"
        )
    return BootstrapOutcome.EXISTS
