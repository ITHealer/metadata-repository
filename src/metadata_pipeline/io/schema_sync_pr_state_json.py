"""Read and write the handoff state for schema-sync PR workflow steps."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from metadata_pipeline.domain.schema_sync_pr import SchemaSyncPullRequestState
from metadata_pipeline.io.atomic_text import write_text_if_changed


class SchemaSyncPullRequestStateError(ValueError):
    """Raised when persisted PR state is missing or invalid."""


def load_schema_sync_pr_state(path: Path) -> SchemaSyncPullRequestState:
    """Load a strict state document written by the prepare step."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return SchemaSyncPullRequestState.model_validate(payload)
    except (FileNotFoundError, OSError, json.JSONDecodeError, ValidationError) as error:
        raise SchemaSyncPullRequestStateError(
            f"unable to load schema-sync PR state {path}: {error}"
        ) from error


def write_schema_sync_pr_state(path: Path, state: SchemaSyncPullRequestState) -> bool:
    """Write deterministic state without credentials or GitHub response noise."""
    content = json.dumps(state.model_dump(mode="json"), indent=2, sort_keys=True)
    return write_text_if_changed(path, content + "\n")
