"""Deterministic JSONL output for semantic chunk dry-runs."""

from __future__ import annotations

import json
from pathlib import Path

from metadata_pipeline.domain.published import Chunk
from metadata_pipeline.io.atomic_text import write_text_if_changed


def dump_chunks(chunks: tuple[Chunk, ...]) -> str:
    """Serialize chunks in stable ID and JSON-key order."""
    return "".join(
        json.dumps(chunk.model_dump(mode="json"), ensure_ascii=False, sort_keys=True) + "\n"
        for chunk in sorted(chunks, key=lambda item: item.chunk_id)
    )


def write_chunks(path: Path, chunks: tuple[Chunk, ...]) -> bool:
    """Atomically write changed chunk JSONL."""
    return write_text_if_changed(path, dump_chunks(chunks))
