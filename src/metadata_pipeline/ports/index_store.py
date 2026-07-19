"""Provider-neutral storage boundary for versioned chunk manifests."""

from __future__ import annotations

from typing import Protocol

from metadata_pipeline.domain.index import IndexManifest


class IndexStoreError(RuntimeError):
    """Raised when an index store cannot load or atomically persist a manifest."""


class IndexStore(Protocol):
    """Load and save complete index snapshots."""

    def load(self) -> IndexManifest:
        """Load the current snapshot, or an empty snapshot when absent."""

    def save(self, manifest: IndexManifest) -> bool:
        """Atomically save a changed snapshot and report whether bytes changed."""
