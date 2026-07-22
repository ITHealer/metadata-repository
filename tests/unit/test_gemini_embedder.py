"""Network-free tests for Gemini embedding task semantics and validation."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import errors

from metadata_pipeline.adapters.embedding.gemini import GeminiEmbedder
from metadata_pipeline.ports.embedder import EmbeddingError


@dataclass
class FakeModels:
    responses: list[Any]
    calls: list[Any]

    def embed_content(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _response(*vectors: tuple[float, ...]) -> Any:
    return SimpleNamespace(embeddings=[SimpleNamespace(values=list(vector)) for vector in vectors])


def test_gemini_uses_distinct_document_and_query_task_types() -> None:
    models = FakeModels([_response((3.0, 4.0)), _response((0.0, 2.0))], [])
    embedder = GeminiEmbedder(
        model="gemini-embedding-001",
        dimension=2,
        max_retries=0,
        client=SimpleNamespace(models=models),
    )

    documents = embedder.embed_documents(("document",))
    query = embedder.embed_query("question")

    assert documents == ((0.6, 0.8),)
    assert query == (0.0, 1.0)
    assert models.calls[0]["config"].task_type == "RETRIEVAL_DOCUMENT"
    assert models.calls[1]["config"].task_type == "RETRIEVAL_QUERY"


def test_gemini_retries_429_and_validates_dimension() -> None:
    models = FakeModels(
        [errors.APIError(429, {}), _response((1.0, 2.0, 3.0))],
        [],
    )
    sleeps: list[float] = []
    embedder = GeminiEmbedder(
        model="gemini-embedding-001",
        dimension=2,
        max_retries=1,
        client=SimpleNamespace(models=models),
        sleep=sleeps.append,
    )

    with pytest.raises(EmbeddingError, match="dimension mismatch"):
        embedder.embed_query("question")

    assert sleeps == [1.0]
