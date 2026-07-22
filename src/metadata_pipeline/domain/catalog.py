"""Database profile contract for the repository metadata catalog."""

from __future__ import annotations

from typing import Optional

from pydantic import Field, field_validator, model_validator

from metadata_pipeline.domain.review import StrictModel


class DatabaseProfile(StrictModel):
    """Reviewed configuration that maps one repository key to one ClickHouse database."""

    enabled: bool = True
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9_]*$")
    display_name: str = Field(min_length=1)
    clickhouse_database: str = Field(min_length=1)
    description: str = Field(min_length=1)
    tables: tuple[str, ...] = ()
    scheduled_sync: bool = False
    tbls_dsn_env: Optional[str] = Field(  # noqa: UP007 - Python 3.9 runtime support
        default=None,
        pattern=r"^[A-Z][A-Z0-9_]*$",
    )

    @field_validator("tables")
    @classmethod
    def require_unique_table_allowlist(cls, tables: tuple[str, ...]) -> tuple[str, ...]:
        """Reject ambiguous or unsafe table allowlists at configuration load time."""
        if any(not table.strip() for table in tables):
            raise ValueError("table allowlist entries must not be empty")
        if len(set(tables)) != len(tables):
            raise ValueError("table allowlist entries must be unique")
        return tables

    @model_validator(mode="after")
    def require_allowlist_when_enabled(self) -> DatabaseProfile:
        """Keep automatic catalog and scheduled-sync boundaries explicit and safe."""
        if self.enabled and not self.tables:
            raise ValueError("enabled database profiles require at least one allowlisted table")
        if self.scheduled_sync and not self.enabled:
            raise ValueError("scheduled sync requires the database profile to be enabled")
        if self.scheduled_sync and self.tbls_dsn_env is None:
            raise ValueError("scheduled sync requires tbls_dsn_env")
        return self
