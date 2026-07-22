"""Deterministic embedder test double."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FakeEmbedder:
    dimension: int
    document_calls: list[tuple[str, ...]] = field(default_factory=list)
    query_calls: list[str] = field(default_factory=list)

    def embed_documents(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        self.document_calls.append(texts)
        return tuple(self._vector(text) for text in texts)

    def embed_query(self, text: str) -> tuple[float, ...]:
        self.query_calls.append(text)
        return self._vector(text)

    def _vector(self, text: str) -> tuple[float, ...]:
        base = float((sum(text.encode("utf-8")) % 9) + 1)
        return tuple(base + index for index in range(self.dimension))
