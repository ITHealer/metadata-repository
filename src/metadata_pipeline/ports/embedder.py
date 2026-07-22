"""Provider-neutral text embedding boundary."""

from __future__ import annotations

from typing import Protocol


class EmbeddingError(RuntimeError):
    """Raised when vectors cannot be produced safely."""


class Embedder(Protocol):
    """Generate distinct document and query embeddings."""

    def embed_documents(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        """Embed retrieval documents in input order."""
        ...

    def embed_query(self, text: str) -> tuple[float, ...]:
        """Embed one retrieval query."""
        ...
