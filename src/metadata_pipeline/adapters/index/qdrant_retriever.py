"""Semantic retriever composed from embedding and vector-index ports."""

from __future__ import annotations

from dataclasses import dataclass

from metadata_pipeline.domain.retrieval import RetrievalHit
from metadata_pipeline.ports.embedder import Embedder
from metadata_pipeline.ports.vector_index import VectorIndex


@dataclass(frozen=True)
class QdrantRetriever:
    """Embed a query with retrieval semantics, then rank managed Qdrant points."""

    embedder: Embedder
    index: VectorIndex

    def search(self, question: str, top_k: int = 3) -> tuple[RetrievalHit, ...]:
        vector = self.embedder.embed_query(question)
        hits = self.index.search(vector, top_k)
        return tuple(
            RetrievalHit(
                rank=rank,
                chunk_id=hit.chunk_id,
                document_id=hit.document_id,
                score=hit.score,
                content=hit.content,
            )
            for rank, hit in enumerate(hits, start=1)
        )
