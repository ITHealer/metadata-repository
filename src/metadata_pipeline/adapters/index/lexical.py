"""Small deterministic lexical retriever for CI smoke tests."""

from __future__ import annotations

import re

from metadata_pipeline.domain.published import Chunk, ChunkType
from metadata_pipeline.domain.retrieval import RetrievalHit

_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "for",
    "how",
    "is",
    "of",
    "the",
    "to",
    "what",
    "which",
}
_TYPE_HINTS = {
    ChunkType.TABLE_OVERVIEW: {"grain", "purpose", "use", "caveat"},
    ChunkType.COLUMN_GROUP: {"column", "type", "unit", "value", "timezone"},
    ChunkType.RELATIONSHIP: {"join", "relationship", "cardinality", "duplicate"},
    ChunkType.BUSINESS_RULE: {"rule", "calculate", "filter", "deleted"},
    ChunkType.QUALITY_AND_SECURITY: {"quality", "security", "sensitive", "safe"},
}


class LexicalRetriever:
    """Rank approved chunks by inspectable token overlap and stable tie-breaking."""

    def __init__(self, chunks: tuple[Chunk, ...]) -> None:
        self._chunks = tuple(chunk for chunk in chunks if chunk.index_eligible)

    def search(self, question: str, top_k: int = 3) -> tuple[RetrievalHit, ...]:
        """Return the top-k approved chunks; score is deterministic and provider-free."""
        question_tokens = _tokens(question) - _STOP_WORDS
        scored = []
        for chunk in self._chunks:
            content_tokens = _tokens(chunk.content)
            identity_tokens = _tokens(f"{chunk.qualified_name} {chunk.semantic_key}")
            score = len(question_tokens & content_tokens) + 2 * len(
                question_tokens & identity_tokens
            )
            if question_tokens & _TYPE_HINTS[chunk.chunk_type]:
                score += 3
            scored.append((score, chunk.chunk_id, chunk))
        ranked = sorted(scored, key=lambda item: (-item[0], item[1]))[:top_k]
        return tuple(
            RetrievalHit(
                rank=index,
                chunk_id=chunk.chunk_id,
                document_id=chunk.qualified_name,
                score=score,
                content=chunk.content,
            )
            for index, (score, _, chunk) in enumerate(ranked, start=1)
        )


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]+", value.lower()))
