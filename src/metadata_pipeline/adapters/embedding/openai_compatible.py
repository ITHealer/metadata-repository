"""Embedding adapter for an OpenAI-compatible model gateway."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    OpenAI,
    OpenAIError,
    RateLimitError,
)

from metadata_pipeline.io.index_settings import IndexSettings
from metadata_pipeline.ports.embedder import EmbeddingError

_BATCH_SIZE = 100


@dataclass(frozen=True)
class OpenAICompatibleEmbedder:
    """Create normalized vectors through the gateway's standard embeddings endpoint."""

    model: str
    dimension: int
    client: Any

    @classmethod
    def from_settings(cls, settings: IndexSettings) -> OpenAICompatibleEmbedder:
        """Build one bounded-retry SDK client from the shared gateway credentials."""
        client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout=settings.timeout_seconds,
            max_retries=settings.max_retries,
        )
        return cls(
            model=settings.embedding_model,
            dimension=settings.embedding_dimension,
            client=client,
        )

    def embed_documents(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        vectors: list[tuple[float, ...]] = []
        for start in range(0, len(texts), _BATCH_SIZE):
            vectors.extend(self._embed(texts[start : start + _BATCH_SIZE]))
        return tuple(vectors)

    def embed_query(self, text: str) -> tuple[float, ...]:
        return self._embed((text,))[0]

    def _embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        if not texts or any(not text.strip() for text in texts):
            raise EmbeddingError("embedding inputs must contain non-empty text")
        try:
            response = self.client.embeddings.create(
                model=self.model,
                input=list(texts),
                dimensions=self.dimension,
                encoding_format="float",
            )
            ordered = sorted(response.data, key=lambda item: item.index)
            vectors = tuple(
                _normalize(tuple(float(value) for value in item.embedding)) for item in ordered
            )
            _validate_vectors(vectors, len(texts), self.dimension)
            return vectors
        except EmbeddingError:
            raise
        except APITimeoutError as error:
            raise EmbeddingError("embedding gateway timed out after bounded SDK retries") from error
        except RateLimitError as error:
            raise EmbeddingError("embedding gateway rate limit persisted after retries") from error
        except APIConnectionError as error:
            raise EmbeddingError("embedding gateway connection failed after retries") from error
        except APIStatusError as error:
            raise EmbeddingError(
                f"embedding gateway returned HTTP {error.status_code} after retries"
            ) from error
        except OpenAIError as error:
            raise EmbeddingError("embedding gateway request failed") from error


def _normalize(vector: tuple[float, ...]) -> tuple[float, ...]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        raise EmbeddingError("embedding provider returned a zero vector")
    return tuple(value / norm for value in vector)


def _validate_vectors(
    vectors: tuple[tuple[float, ...], ...],
    expected_count: int,
    dimension: int,
) -> None:
    if len(vectors) != expected_count:
        raise EmbeddingError(
            f"embedding count mismatch: expected {expected_count}, got {len(vectors)}"
        )
    if any(len(vector) != dimension for vector in vectors):
        raise EmbeddingError(f"embedding dimension mismatch: expected {dimension}")
