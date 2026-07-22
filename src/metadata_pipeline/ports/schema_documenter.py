"""Boundary for generating raw schema documentation from an external database."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from metadata_pipeline.domain.catalog import DatabaseProfile


class SchemaDocumenterError(RuntimeError):
    """Raised when external schema documentation cannot be generated safely."""


class SchemaDocumenter(Protocol):
    """Generate and lint one complete database snapshot into a staging directory."""

    def generate(
        self,
        *,
        profile: DatabaseProfile,
        config_path: Path,
        output_dir: Path,
        dsn: str,
    ) -> None:
        """Write a complete validated raw snapshot or raise before catalog publication."""
