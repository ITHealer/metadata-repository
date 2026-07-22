"""Runtime settings for scheduled schema synchronization."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from metadata_pipeline.domain.catalog import DatabaseProfile
from metadata_pipeline.io.runtime_environment import load_runtime_environment


class SchemaSyncConfigurationError(ValueError):
    """Raised before external work when scheduled-sync settings are incomplete."""


@dataclass(frozen=True)
class SchemaSyncSettings:
    """Validated feature flag plus secret lookup without retaining DSNs in reports."""

    enabled: bool
    environ: Mapping[str, str]

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> SchemaSyncSettings:
        """Build settings from process environment or a supplied test mapping."""
        values = load_runtime_environment(environ)
        return cls(
            enabled=_boolean(values, "SCHEMA_SYNC_ENABLED", default=False),
            environ=values,
        )

    def dsn_for(self, profile: DatabaseProfile) -> str:
        """Resolve one configured secret by name without exposing its value in errors."""
        variable = profile.tbls_dsn_env
        if variable is None:
            raise SchemaSyncConfigurationError(
                f"{profile.key}: scheduled profile has no tbls_dsn_env"
            )
        value = self.environ.get(variable, "").strip()
        if not value:
            raise SchemaSyncConfigurationError(
                f"{profile.key}: required environment variable {variable} is not set"
            )
        return value


def _boolean(values: Mapping[str, str], name: str, *, default: bool) -> bool:
    raw = values.get(name)
    if raw is None or not raw.strip():
        return default
    normalized = raw.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise SchemaSyncConfigurationError(f"{name} must be 'true' or 'false'")
