"""Unit tests for semantic chunk construction and co-location validation."""

import json
from pathlib import Path

from metadata_pipeline.application.build_chunks import build_chunks
from metadata_pipeline.domain.hashing import canonical_sha256
from metadata_pipeline.domain.published import Chunk, ChunkType, PublishedDocument
from metadata_pipeline.io.chunk_jsonl import dump_chunks, write_chunks
from metadata_pipeline.validation.chunks import validate_chunks


def test_build_chunks_covers_semantic_units_with_stable_ids(
    published_document: PublishedDocument,
) -> None:
    chunks = build_chunks(published_document)
    assert len(chunks) == 10
    assert not validate_chunks(published_document, chunks, Path("chunks.jsonl"))
    assert chunks == tuple(sorted(chunks, key=lambda item: item.chunk_id))
    assert sum(chunk.chunk_type is ChunkType.TABLE_OVERVIEW for chunk in chunks) == 1
    assert sum(chunk.chunk_type is ChunkType.COLUMN_GROUP for chunk in chunks) == 6
    assert all(
        chunk.body_hash == canonical_sha256(chunk.model_dump(mode="json", exclude={"body_hash"}))
        for chunk in chunks
    )
    relation = next(chunk for chunk in chunks if chunk.chunk_type is ChunkType.RELATIONSHIP)
    for value in (
        "orders.customer_id = customers.customer_id",
        "many_to_one",
        "unknown",
        "ClickHouse does not enforce",
    ):
        assert value in relation.content


def test_chunk_validator_reports_missing_relationship_context(
    published_document: PublishedDocument,
) -> None:
    chunks = list(build_chunks(published_document))
    index = next(
        index for index, chunk in enumerate(chunks) if chunk.chunk_type is ChunkType.RELATIONSHIP
    )
    chunks[index] = Chunk.model_validate(
        chunks[index].model_copy(update={"content": published_document.qualified_name}).model_dump()
    )
    issues = validate_chunks(published_document, tuple(chunks), Path("chunks.jsonl"))
    assert "incomplete_relationship_context" in {issue.code for issue in issues}
    assert "invalid_chunk_body_hash" in {issue.code for issue in issues}


def test_chunk_jsonl_is_deterministic_and_atomic(
    tmp_path: Path,
    published_document: PublishedDocument,
) -> None:
    chunks = build_chunks(published_document)
    content = dump_chunks(tuple(reversed(chunks)))
    rows = tuple(json.loads(line) for line in content.splitlines())
    assert [row["chunk_id"] for row in rows] == sorted(row["chunk_id"] for row in rows)
    path = tmp_path / "chunks.jsonl"
    assert write_chunks(path, chunks) is True
    assert write_chunks(path, chunks) is False
