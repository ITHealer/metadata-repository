"""Stable JSON output for verified VectorDB apply results."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from metadata_pipeline.domain.vector_apply import VectorApplySummary
from metadata_pipeline.io.atomic_text import write_text_if_changed


class ApplySummaryError(ValueError):
    """Raised when a persisted apply summary is invalid."""


def load_apply_summary(path: Path) -> VectorApplySummary:
    try:
        return VectorApplySummary.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as error:
        raise ApplySummaryError(f"unable to load vector apply summary {path}: {error}") from error


def write_apply_summary(path: Path, summary: VectorApplySummary) -> bool:
    content = json.dumps(summary.model_dump(mode="json"), indent=2, sort_keys=True)
    return write_text_if_changed(path, content + "\n")
