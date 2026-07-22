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
        "OPENAI_API_KEY": "gateway-secret",
        "OPENAI_BASE_URL": "https://gateway.example/v1",
        "QDRANT_URL": "https://qdrant.example",
    }
    settings = IndexSettings.from_env(base)

    assert settings.embedding_dimension == 768
    assert settings.embedding_provider == "openai_compatible"
    assert settings.openai_base_url == "https://gateway.example/v1"
    assert "gateway-secret" not in repr(settings)

    with pytest.raises(IndexConfigurationError, match="QDRANT_COLLECTION"):
        IndexSettings.from_env(base | {"QDRANT_COLLECTION": "wrong"})


def test_enabled_index_settings_reject_missing_credentials() -> None:
    with pytest.raises(IndexConfigurationError, match="OPENAI_API_KEY"):
        IndexSettings.from_env(
            {
                "INDEX_APPLY_ENABLED": "true",
                "QDRANT_URL": "http://localhost:6333",
            }
        )


def test_enabled_index_settings_allow_local_qdrant_without_api_key() -> None:
    settings = IndexSettings.from_env(
        {
            "INDEX_APPLY_ENABLED": "true",
            "OPENAI_API_KEY": "gateway-secret",
            "OPENAI_BASE_URL": "https://gateway.example/v1",
            "QDRANT_URL": "http://localhost:6333",
            "QDRANT_API_KEY": "",
        }
    )

    assert settings.qdrant_url == "http://localhost:6333"
    assert settings.qdrant_api_key == ""
