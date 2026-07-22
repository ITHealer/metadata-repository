"""Tests for disabled defaults and strict live VectorDB settings."""

import pytest

from metadata_pipeline.io.index_settings import IndexConfigurationError, IndexSettings


def test_disabled_index_settings_require_no_external_credentials() -> None:
    settings = IndexSettings.from_env({"INDEX_APPLY_ENABLED": "false"})

    assert settings.enabled is False
    assert "api_key" not in repr(settings)


def test_enabled_index_settings_require_secrets_and_matching_collection() -> None:
    base = {
        "INDEX_APPLY_ENABLED": "true",
        "GEMINI_API_KEY": "gemini-secret",
        "QDRANT_URL": "https://qdrant.example",
        "QDRANT_API_KEY": "qdrant-secret",
    }
    settings = IndexSettings.from_env(base)

    assert settings.embedding_dimension == 768
    assert "gemini-secret" not in repr(settings)
    assert "qdrant-secret" not in repr(settings)

    with pytest.raises(IndexConfigurationError, match="QDRANT_COLLECTION"):
        IndexSettings.from_env(base | {"QDRANT_COLLECTION": "wrong"})


def test_enabled_index_settings_reject_missing_credentials() -> None:
    with pytest.raises(IndexConfigurationError, match="QDRANT_URL"):
        IndexSettings.from_env({"INDEX_APPLY_ENABLED": "true"})
