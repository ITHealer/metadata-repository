"""Idempotency, ordering, and recovery tests for VectorDB apply."""

from __future__ import annotations

import pytest

from metadata_pipeline.application.apply_index import apply_index
from metadata_pipeline.application.index_changes import build_index_manifest
from metadata_pipeline.domain.hashing import canonical_sha256
from metadata_pipeline.domain.published import Chunk
from metadata_pipeline.domain.vector_apply import ApplyOutcome
from metadata_pipeline.io.index_settings import IndexSettings
from metadata_pipeline.ports.embedder import EmbeddingError
from metadata_pipeline.ports.vector_index import VectorIndexError, VectorPoint
from tests.unit.fakes.fake_embedder import FakeEmbedder
from tests.unit.fakes.fake_vector_index import FakeVectorIndex


def _settings(*, enabled: bool = True, dimension: int = 3) -> IndexSettings:
    return IndexSettings(
        enabled=enabled,
        embedding_model="test-model",
        embedding_dimension=dimension,
        qdrant_url="https://qdrant.example",
        qdrant_api_key="secret",
        qdrant_collection=f"metadata__test_model__{dimension}",
        openai_api_key="secret",
    )


def test_disabled_apply_constructs_no_clients(approved_chunks: tuple[Chunk, ...]) -> None:
    manifest = build_index_manifest(approved_chunks, "a" * 40)

    summary = apply_index(
        manifest=manifest,
        settings=_settings(enabled=False),
        embedder=None,
        index=None,
    )

    assert summary.outcome is ApplyOutcome.DISABLED
    assert summary.verified is False


def test_initial_apply_then_identical_retry_is_idempotent(
    approved_chunks: tuple[Chunk, ...],
) -> None:
    manifest = build_index_manifest(approved_chunks, "a" * 40)
    embedder = FakeEmbedder(3)
    index = FakeVectorIndex(3)

    first = apply_index(manifest=manifest, settings=_settings(), embedder=embedder, index=index)
    second = apply_index(manifest=manifest, settings=_settings(), embedder=embedder, index=index)

    assert first.outcome is ApplyOutcome.APPLIED
    assert first.upserted_count == len(approved_chunks)
    assert second.outcome is ApplyOutcome.NOOP
    assert second.upserted_count == 0
    assert len(embedder.document_calls) == 1


def test_apply_upserts_before_deleting_stale_points(
    approved_chunks: tuple[Chunk, ...],
) -> None:
    first_manifest = build_index_manifest(approved_chunks[:2], "a" * 40)
    index = FakeVectorIndex(3)
    embedder = FakeEmbedder(3)
    apply_index(manifest=first_manifest, settings=_settings(), embedder=embedder, index=index)
    stale = next(iter(index.points.values()))
    replacement = _changed_chunk(approved_chunks[2], "updated content")
    desired = build_index_manifest((replacement,), "b" * 40)
    index.operations.clear()

    summary = apply_index(manifest=desired, settings=_settings(), embedder=embedder, index=index)

    assert summary.upserted_count == 1
    assert summary.deleted_count == 2
    assert index.operations == ["upsert:1", "delete:2"]
    assert stale.point_id not in index.points


def test_partial_upsert_never_deletes_and_retry_skips_completed_points(
    approved_chunks: tuple[Chunk, ...],
) -> None:
    manifest = build_index_manifest(approved_chunks[:3], "a" * 40)
    index = FakeVectorIndex(3, fail_upsert_after=1)
    stale = VectorPoint(
        point_id="point:stale",
        chunk_id="stale",
        body_hash="f" * 64,
        vector=(1.0, 2.0, 3.0),
        payload={"document_id": "stale", "content": "stale"},
    )
    index.points[stale.point_id] = stale
    embedder = FakeEmbedder(3)

    with pytest.raises(VectorIndexError, match="partial upsert"):
        apply_index(manifest=manifest, settings=_settings(), embedder=embedder, index=index)

    assert "delete:1" not in index.operations
    retry = apply_index(manifest=manifest, settings=_settings(), embedder=embedder, index=index)
    assert retry.outcome is ApplyOutcome.APPLIED
    assert retry.upserted_count == 2
    assert retry.deleted_count == 1


def test_dimension_mismatch_fails_before_any_upsert(
    approved_chunks: tuple[Chunk, ...],
) -> None:
    manifest = build_index_manifest(approved_chunks[:1], "a" * 40)
    index = FakeVectorIndex(3)

    with pytest.raises(EmbeddingError, match="dimension mismatch"):
        apply_index(
            manifest=manifest,
            settings=_settings(dimension=4),
            embedder=FakeEmbedder(3),
            index=index,
        )

    assert not index.operations


def _changed_chunk(chunk: Chunk, content: str) -> Chunk:
    payload = chunk.model_dump(mode="json", exclude={"body_hash"})
    payload["content"] = content
    payload["body_hash"] = canonical_sha256(payload)
    return Chunk.model_validate(payload)
