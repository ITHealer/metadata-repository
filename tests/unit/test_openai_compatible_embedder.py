"""Network-free tests for the OpenAI-compatible embedding adapter."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from metadata_pipeline.adapters.embedding.openai_compatible import OpenAICompatibleEmbedder
from metadata_pipeline.ports.embedder import EmbeddingError


@dataclass
class FakeEmbeddings:
    responses: list[Any]
    calls: list[Any]

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.responses.pop(0)


def _response(*vectors: tuple[float, ...]) -> Any:
    return SimpleNamespace(
        data=[
            SimpleNamespace(index=index, embedding=list(vector))
            for index, vector in enumerate(vectors)
        ]
    )


def test_embedder_uses_gateway_model_dimension_and_normalizes_vectors() -> None:
    embeddings = FakeEmbeddings([_response((3.0, 4.0)), _response((0.0, 2.0))], [])
    embedder = OpenAICompatibleEmbedder(
        model="gemini-embedding-001",
        dimension=2,
        client=SimpleNamespace(embeddings=embeddings),
    )

    documents = embedder.embed_documents(("document",))
    query = embedder.embed_query("question")

    assert documents == ((0.6, 0.8),)
    assert query == ((0.0, 1.0))
    assert embeddings.calls[0] == {
        "model": "gemini-embedding-001",
        "input": ["document"],
        "dimensions": 2,
        "encoding_format": "float",
    }
    assert embeddings.calls[1]["input"] == ["question"]


def test_embedder_validates_count_and_dimension() -> None:
    embeddings = FakeEmbeddings([_response((1.0, 2.0, 3.0))], [])
    embedder = OpenAICompatibleEmbedder(
        model="gemini-embedding-001",
        dimension=2,
        client=SimpleNamespace(embeddings=embeddings),
    )

    with pytest.raises(EmbeddingError, match="dimension mismatch"):
        embedder.embed_query("question")


def test_embedder_rejects_empty_inputs_before_calling_gateway() -> None:
    embeddings = FakeEmbeddings([], [])
    embedder = OpenAICompatibleEmbedder(
        model="gemini-embedding-001",
        dimension=2,
        client=SimpleNamespace(embeddings=embeddings),
    )

    with pytest.raises(EmbeddingError, match="non-empty"):
        embedder.embed_documents(("",))

    assert embeddings.calls == []
