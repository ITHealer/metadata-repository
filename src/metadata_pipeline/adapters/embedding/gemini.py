"""Gemini embedding adapter with task-specific semantics and bounded retries."""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from google import genai
from google.genai import errors, types

from metadata_pipeline.io.index_settings import IndexSettings
from metadata_pipeline.ports.embedder import EmbeddingError

_BATCH_SIZE = 100


@dataclass(frozen=True)
class GeminiEmbedder:
    """Use RETRIEVAL_DOCUMENT for index data and RETRIEVAL_QUERY for questions."""

    model: str
    dimension: int
    max_retries: int
    client: Any
    sleep: Callable[[float], None] = time.sleep

    @classmethod
    def from_settings(cls, settings: IndexSettings) -> GeminiEmbedder:
        client = genai.Client(
            api_key=settings.gemini_api_key,
            http_options=types.HttpOptions(timeout=int(settings.timeout_seconds * 1000)),
        )
        return cls(
            model=settings.embedding_model,
            dimension=settings.embedding_dimension,
            max_retries=settings.max_retries,
            client=client,
        )

    def embed_documents(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        vectors: list[tuple[float, ...]] = []
        for start in range(0, len(texts), _BATCH_SIZE):
            vectors.extend(self._embed(texts[start : start + _BATCH_SIZE], "RETRIEVAL_DOCUMENT"))
        return tuple(vectors)

    def embed_query(self, text: str) -> tuple[float, ...]:
        return self._embed((text,), "RETRIEVAL_QUERY")[0]

    def _embed(self, texts: tuple[str, ...], task_type: str) -> tuple[tuple[float, ...], ...]:
        if not texts or any(not text.strip() for text in texts):
            raise EmbeddingError("embedding inputs must contain non-empty text")
        attempts = self.max_retries + 1
        for attempt in range(1, attempts + 1):
            try:
                response = self.client.models.embed_content(
                    model=self.model,
                    contents=list(texts),
                    config=types.EmbedContentConfig(
                        task_type=task_type,
                        output_dimensionality=self.dimension,
                    ),
                )
                embeddings = response.embeddings or []
                vectors = tuple(
                    _normalize(tuple(float(value) for value in (embedding.values or [])))
                    for embedding in embeddings
                )
                _validate_vectors(vectors, len(texts), self.dimension)
                return vectors
            except errors.APIError as error:
                retryable = error.code == 429 or error.code >= 500
                if not retryable or attempt == attempts:
                    raise EmbeddingError(
                        f"Gemini embedding failed after {attempt} attempt(s): API {error.code}"
                    ) from error
                self.sleep(float(min(2 ** (attempt - 1), 5)))
        raise EmbeddingError("Gemini embedding failed without a provider response")


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
