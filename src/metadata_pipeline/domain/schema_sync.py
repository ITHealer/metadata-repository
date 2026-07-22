"""Versioned result contracts for staged scheduled schema synchronization."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import Field, model_validator

from metadata_pipeline.domain.review import StrictModel


class SchemaSyncOutcome(str, Enum):
    """Operator-visible outcomes that do not conflate no-op with failure."""

    DISABLED = "disabled"
    NOOP = "noop"
    CHANGED = "changed"
    MANUAL_CLEANUP_REQUIRED = "manual_cleanup_required"


class DatabaseSchemaSyncReport(StrictModel):
    """Deterministic table and path changes for one repository database key."""

    key: str = Field(min_length=1)
    clickhouse_database: str = Field(min_length=1)
    added: tuple[str, ...] = ()
    modified: tuple[str, ...] = ()
    deleted: tuple[str, ...] = ()
    raw_changed_paths: tuple[str, ...] = ()
    review_paths: tuple[str, ...] = ()

    @property
    def has_changes(self) -> bool:
        """Return whether the supported technical schema contract changed."""
        return bool(self.added or self.modified or self.deleted)

    @model_validator(mode="after")
    def require_sorted_unique_values(self) -> DatabaseSchemaSyncReport:
        """Keep reports stable for Git diffs, PR bodies, and notification payloads."""
        for field in (
            "added",
            "modified",
            "deleted",
            "raw_changed_paths",
            "review_paths",
        ):
            values = getattr(self, field)
            if values != tuple(sorted(set(values))):
                raise ValueError(f"{field} must be sorted and unique")
        return self


class ScheduledSchemaSyncReport(StrictModel):
    """Complete non-secret output of one scheduled-sync invocation."""

    format_version: Literal["schema-sync-report-v1"] = "schema-sync-report-v1"
    run_id: str = Field(min_length=1)
    outcome: SchemaSyncOutcome
    databases: tuple[DatabaseSchemaSyncReport, ...] = ()
    warnings: tuple[str, ...] = ()
    manual_cleanup: tuple[str, ...] = ()

    @model_validator(mode="after")
    def require_consistent_outcome(self) -> ScheduledSchemaSyncReport:
        """Prevent a report from claiming no-op while carrying schema changes."""
        keys = tuple(item.key for item in self.databases)
        if keys != tuple(sorted(set(keys))):
            raise ValueError("database reports must be sorted and unique by key")
        changed = any(item.has_changes for item in self.databases)
        if self.outcome in {SchemaSyncOutcome.DISABLED, SchemaSyncOutcome.NOOP} and changed:
            raise ValueError("disabled/noop reports cannot contain schema changes")
        if self.outcome is SchemaSyncOutcome.CHANGED and not changed:
            raise ValueError("changed report must contain at least one schema change")
        if self.outcome is SchemaSyncOutcome.MANUAL_CLEANUP_REQUIRED and (
            not changed or not self.manual_cleanup
        ):
            raise ValueError("manual cleanup outcome requires changes and cleanup details")
        if self.manual_cleanup != tuple(sorted(set(self.manual_cleanup))):
            raise ValueError("manual_cleanup must be sorted and unique")
        return self
