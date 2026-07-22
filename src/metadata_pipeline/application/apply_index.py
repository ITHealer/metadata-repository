"""Idempotently reconcile a complete desired manifest with actual VectorDB state."""

from __future__ import annotations

from metadata_pipeline.domain.index import IndexManifest
from metadata_pipeline.domain.published import Chunk
from metadata_pipeline.domain.vector_apply import ApplyOutcome, VectorApplySummary
from metadata_pipeline.io.index_settings import IndexSettings
from metadata_pipeline.ports.embedder import Embedder, EmbeddingError
from metadata_pipeline.ports.vector_index import (
    VectorChunkState,
    VectorIndex,
    VectorIndexError,
    VectorPoint,
)


def apply_index(
    *,
    manifest: IndexManifest,
    settings: IndexSettings,
    embedder: Embedder | None,
    index: VectorIndex | None,
) -> VectorApplySummary:
    """Upsert correct content, then delete stale points, and verify exact managed state."""
    document_count = len(manifest.documents)
    desired = _desired_chunks(manifest)
    if not settings.enabled:
        return VectorApplySummary(
            outcome=ApplyOutcome.DISABLED,
            collection=settings.qdrant_collection,
            manifest_hash=manifest.manifest_hash,
            document_count=document_count,
            chunk_count=len(desired),
            upserted_count=0,
            deleted_count=0,
            skipped_count=len(desired),
            verified=False,
        )
    if embedder is None or index is None:
        raise ValueError("enabled index apply requires an embedder and vector index")

    actual = _state_by_chunk(index)
    upsert_ids = tuple(
        chunk_id
        for chunk_id, chunk in desired.items()
        if chunk_id not in actual or actual[chunk_id].body_hash != chunk.body_hash
    )
    delete_ids = tuple(sorted(set(actual) - set(desired)))
    skipped = len(desired) - len(upsert_ids)

    if upsert_ids:
        vectors = embedder.embed_documents(tuple(desired[item].content for item in upsert_ids))
        if len(vectors) != len(upsert_ids):
            raise EmbeddingError("embedding provider returned an unexpected vector count")
        points = tuple(
            _vector_point(
                desired[chunk_id],
                vector,
                manifest.manifest_hash,
                settings,
                index.point_id_for_chunk(chunk_id),
            )
            for chunk_id, vector in zip(upsert_ids, vectors)
        )
        index.upsert(points)
    if delete_ids:
        index.delete(tuple(actual[chunk_id].point_id for chunk_id in delete_ids))

    _verify_state(index, desired)
    outcome = ApplyOutcome.APPLIED if upsert_ids or delete_ids else ApplyOutcome.NOOP
    return VectorApplySummary(
        outcome=outcome,
        collection=settings.qdrant_collection,
        manifest_hash=manifest.manifest_hash,
        document_count=document_count,
        chunk_count=len(desired),
        upserted_count=len(upsert_ids),
        deleted_count=len(delete_ids),
        skipped_count=skipped,
        verified=True,
    )


def _desired_chunks(manifest: IndexManifest) -> dict[str, Chunk]:
    desired = {
        chunk.chunk_id: chunk for document in manifest.documents for chunk in document.chunks
    }
    expected = sum(len(document.chunks) for document in manifest.documents)
    if len(desired) != expected:
        raise ValueError("desired manifest contains duplicate chunk IDs")
    return dict(sorted(desired.items()))


def _vector_point(
    chunk: Chunk,
    vector: tuple[float, ...],
    manifest_hash: str,
    settings: IndexSettings,
    point_id: str,
) -> VectorPoint:
    if len(vector) != settings.embedding_dimension:
        raise EmbeddingError(
            "embedding dimension mismatch: "
            f"expected {settings.embedding_dimension}, got {len(vector)}"
        )
    payload: dict[str, object] = {
        "managed_by": "metadata-pipeline",
        "chunk_id": chunk.chunk_id,
        "body_hash": chunk.body_hash,
        "database": chunk.database,
        "table": chunk.table,
        "document_id": chunk.qualified_name,
        "chunk_type": chunk.chunk_type.value,
        "schema_hash": chunk.schema_hash,
        "source_review_commit": chunk.source_review_commit,
        "generator_model": chunk.generator_model,
        "prompt_version": chunk.prompt_version,
        "manifest_hash": manifest_hash,
        "embedding_model": settings.embedding_model,
        "embedding_dimension": settings.embedding_dimension,
        "content": chunk.content,
    }
    return VectorPoint(
        point_id=point_id,
        chunk_id=chunk.chunk_id,
        body_hash=chunk.body_hash,
        vector=vector,
        payload=payload,
    )


def _verify_state(index: VectorIndex, desired: dict[str, Chunk]) -> None:
    verified = _state_by_chunk(index)
    if set(verified) != set(desired):
        raise VectorIndexError("post-apply verification found missing or stale managed chunk IDs")
    mismatched = tuple(
        chunk_id
        for chunk_id, chunk in desired.items()
        if verified[chunk_id].body_hash != chunk.body_hash
    )
    if mismatched:
        raise VectorIndexError(
            f"post-apply verification found {len(mismatched)} body hash mismatch(es)"
        )


def _state_by_chunk(index: VectorIndex) -> dict[str, VectorChunkState]:
    states = index.list_chunk_states()
    by_chunk: dict[str, VectorChunkState] = {state.chunk_id: state for state in states}
    if len(by_chunk) != len(states):
        raise VectorIndexError("VectorDB contains duplicate managed chunk IDs")
    return by_chunk
