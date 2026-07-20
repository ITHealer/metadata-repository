"""Atomic JSON persistence for generated metadata candidates."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from metadata_pipeline.domain.candidate import GeneratedCandidate
from metadata_pipeline.io.atomic_text import write_text_if_changed


class CandidateFileError(ValueError):
    """Raised when a persisted candidate is missing or violates its contract."""


def load_candidate(path: Path) -> GeneratedCandidate:
    """Load one strict candidate artifact from JSON."""
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise CandidateFileError(f"candidate not found: {path}") from error
    try:
        return GeneratedCandidate.model_validate_json(content)
    except ValidationError as error:
        raise CandidateFileError(f"invalid candidate {path}: {error}") from error


def write_candidate(path: Path, candidate: GeneratedCandidate) -> bool:
    """Persist deterministic, reviewable JSON only when its bytes changed."""
    content = (
        json.dumps(
            candidate.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return write_text_if_changed(path, content)
