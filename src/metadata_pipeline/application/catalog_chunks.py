"""Build one approved-only chunk artifact from all database candidates."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from metadata_pipeline.application.build_chunks import build_chunks
from metadata_pipeline.application.candidate_state import validate_candidate_integrity
from metadata_pipeline.domain.candidate import CandidateState
from metadata_pipeline.domain.published import Chunk
from metadata_pipeline.io.candidate_json import load_candidate
from metadata_pipeline.io.chunk_jsonl import write_chunks
from metadata_pipeline.validation.chunks import validate_chunks


class CatalogChunkError(ValueError):
    """Raised before output when promoted candidates cannot produce safe chunks."""


@dataclass(frozen=True)
class CatalogChunkBatch:
    """Validated approved chunks collected across isolated database directories."""

    chunks: tuple[Chunk, ...]
    promoted_documents: int


def prepare_catalog_chunks(structured_dirs: tuple[Path, ...]) -> CatalogChunkBatch:
    """Load promoted candidates, verify integrity, and build globally unique chunks."""
    chunks: list[Chunk] = []
    promoted_documents = 0
    for structured_dir in sorted(structured_dirs):
        for path in sorted(structured_dir.glob("*.json")):
            candidate = load_candidate(path)
            validate_candidate_integrity(candidate)
            if candidate.state is not CandidateState.PROMOTED:
                continue
            document_chunks = build_chunks(candidate.document)
            issues = validate_chunks(candidate.document, document_chunks, path)
            if issues:
                details = "; ".join(f"{issue.code}: {issue.message}" for issue in issues)
                raise CatalogChunkError(f"{path}: {details}")
            promoted_documents += 1
            chunks.extend(document_chunks)
    chunk_ids = [chunk.chunk_id for chunk in chunks]
    if len(chunk_ids) != len(set(chunk_ids)):
        raise CatalogChunkError("duplicate chunk IDs found across database candidates")
    return CatalogChunkBatch(
        tuple(sorted(chunks, key=lambda item: item.chunk_id)), promoted_documents
    )


def write_catalog_chunks(output: Path, batch: CatalogChunkBatch) -> bool:
    """Write one deterministic JSONL snapshot for post-merge indexing."""
    return write_chunks(output, batch.chunks)
