"""Atomic JSON implementation of the IndexStore port."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from metadata_pipeline.domain.index import IndexManifest
from metadata_pipeline.io.atomic_text import write_text_if_changed
from metadata_pipeline.ports.index_store import IndexStoreError


@dataclass(frozen=True)
class ManifestIndexStore:
    """Persist complete manifests without an external vector database."""

    path: Path

    def load(self) -> IndexManifest:
        """Load a strict manifest; absence represents an empty previous snapshot."""
        if not self.path.exists():
            return IndexManifest.create(source_commit="0000000")
        try:
            payload = self.path.read_text(encoding="utf-8")
            return IndexManifest.model_validate_json(payload)
        except (OSError, ValidationError) as error:
            raise IndexStoreError(f"{self.path}: invalid index manifest: {error}") from error

    def save(self, manifest: IndexManifest) -> bool:
        """Write stable UTF-8 JSON atomically."""
        content = json.dumps(
            manifest.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        try:
            return write_text_if_changed(self.path, content + "\n")
        except OSError as error:
            raise IndexStoreError(
                f"{self.path}: unable to write index manifest: {error}"
            ) from error
