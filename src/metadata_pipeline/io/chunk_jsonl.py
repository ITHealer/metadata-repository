"""Deterministic JSONL output for semantic chunk dry-runs."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

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


def load_chunks(path: Path) -> tuple[Chunk, ...]:
    """Load and validate one Chunk per non-empty JSONL line."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ValueError(f"{path}: unable to read chunk JSONL: {error}") from error
    chunks: list[Chunk] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            chunks.append(Chunk.model_validate_json(line))
        except ValidationError as error:
            raise ValueError(f"{path}:{line_number}: invalid chunk: {error}") from error
    return tuple(chunks)
