"""Database profile contract for the repository metadata catalog."""

from __future__ import annotations

from pydantic import Field, field_validator

from metadata_pipeline.domain.review import StrictModel


class DatabaseProfile(StrictModel):
    """Reviewed configuration that maps one repository key to one ClickHouse database."""

    key: str = Field(pattern=r"^[a-z0-9][a-z0-9_]*$")
    display_name: str = Field(min_length=1)
    clickhouse_database: str = Field(min_length=1)
    description: str = Field(min_length=1)
    tables: tuple[str, ...] = Field(min_length=1)

    @field_validator("tables")
    @classmethod
    def require_unique_table_allowlist(cls, tables: tuple[str, ...]) -> tuple[str, ...]:
        """Reject ambiguous or unsafe table allowlists at configuration load time."""
        if any(not table.strip() for table in tables):
            raise ValueError("table allowlist entries must not be empty")
        if len(set(tables)) != len(tables):
            raise ValueError("table allowlist entries must be unique")
        return tables
