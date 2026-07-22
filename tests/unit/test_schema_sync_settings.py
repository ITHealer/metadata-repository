"""Tests for strict scheduled-sync runtime configuration."""

import pytest

from metadata_pipeline.domain.catalog import DatabaseProfile
from metadata_pipeline.io.schema_sync_settings import (
    SchemaSyncConfigurationError,
    SchemaSyncSettings,
)


def _profile() -> DatabaseProfile:
    return DatabaseProfile(
        enabled=True,
        scheduled_sync=True,
        tbls_dsn_env="TBLS_DSN_EXAMPLE",
        key="example",
        display_name="Example",
        clickhouse_database="example",
        description="Test profile",
        tables=("events",),
    )


def test_defaults_to_disabled_and_does_not_require_a_dsn() -> None:
    settings = SchemaSyncSettings.from_env({})

    assert settings.enabled is False


def test_resolves_dsn_by_configured_environment_name() -> None:
    settings = SchemaSyncSettings.from_env(
        {"SCHEMA_SYNC_ENABLED": "true", "TBLS_DSN_EXAMPLE": "clickhouse://secret"}
    )

    assert settings.enabled is True
    assert settings.dsn_for(_profile()) == "clickhouse://secret"


def test_rejects_invalid_boolean_without_exposing_other_settings() -> None:
    with pytest.raises(SchemaSyncConfigurationError, match="must be 'true' or 'false'"):
        SchemaSyncSettings.from_env(
            {"SCHEMA_SYNC_ENABLED": "yes", "TBLS_DSN_EXAMPLE": "clickhouse://secret"}
        )


def test_missing_dsn_error_names_variable_but_not_a_secret() -> None:
    settings = SchemaSyncSettings.from_env({"SCHEMA_SYNC_ENABLED": "true"})

    with pytest.raises(SchemaSyncConfigurationError, match="TBLS_DSN_EXAMPLE") as error:
        settings.dsn_for(_profile())

    assert "clickhouse://" not in str(error.value)
