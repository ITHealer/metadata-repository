"""Tests for explicit, non-destructive collection bootstrap."""

import pytest

from metadata_pipeline.application.bootstrap_vector_index import (
    BootstrapOutcome,
    bootstrap_vector_index,
)
from metadata_pipeline.io.index_settings import IndexSettings
from metadata_pipeline.ports.vector_index import VectorIndexError
from tests.unit.fakes.fake_vector_index import FakeVectorIndex


def _settings() -> IndexSettings:
    return IndexSettings(
        enabled=True,
        embedding_model="test-model",
        embedding_dimension=3,
        qdrant_collection="metadata__test_model__3",
    )


def test_bootstrap_creates_only_when_absent() -> None:
    index = FakeVectorIndex(3, exists=False)

    assert bootstrap_vector_index(_settings(), index) is BootstrapOutcome.CREATED
    assert bootstrap_vector_index(_settings(), index) is BootstrapOutcome.EXISTS
    assert index.operations == ["create:3:cosine"]


def test_bootstrap_rejects_existing_dimension_mismatch() -> None:
    with pytest.raises(VectorIndexError, match="does not match"):
        bootstrap_vector_index(_settings(), FakeVectorIndex(4))
