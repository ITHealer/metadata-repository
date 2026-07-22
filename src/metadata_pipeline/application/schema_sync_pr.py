"""Provider-neutral decisions for one active scheduled schema-sync Pull Request."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from metadata_pipeline.application.schema_sync_summary import summarize_schema_change
from metadata_pipeline.domain.schema_sync import (
    DatabaseSchemaSyncReport,
    ScheduledSchemaSyncReport,
    SchemaSyncOutcome,
)
from metadata_pipeline.domain.schema_sync_pr import SchemaSyncPullRequest
from metadata_pipeline.ports.schema_source import DatabaseSchema

_ALLOWED_PATH = re.compile(r"^catalog/[a-z0-9][a-z0-9_]*/(?:generated/raw/.+|review/.+)$")
_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class SchemaSyncPullRequestError(ValueError):
    """Raised when PR state or a prospective bot commit is unsafe or ambiguous."""


def resolve_active_schema_sync_pull_request(
    candidates: Sequence[SchemaSyncPullRequest],
) -> SchemaSyncPullRequest | None:
    """Return zero or one active PR and reject an ambiguous automation state."""
    if len(candidates) > 1:
        numbers = ", ".join(str(candidate.number) for candidate in candidates)
        raise SchemaSyncPullRequestError(
            f"multiple open schema-sync Pull Requests found: {numbers}"
        )
    return candidates[0] if candidates else None


def validate_schema_sync_changed_paths(paths: Sequence[str]) -> tuple[str, ...]:
    """Allow only raw technical output and reviewer input in the schema-sync commit."""
    normalized = tuple(sorted(set(paths)))
    unsafe = tuple(path for path in normalized if not _ALLOWED_PATH.fullmatch(path))
    if unsafe:
        raise SchemaSyncPullRequestError(
            "schema sync changed files outside its allowlist: " + ", ".join(unsafe)
        )
    return normalized


def schema_sync_branch_name(run_id: str) -> str:
    """Build a safe, deterministic automation branch name for a new PR."""
    if not _SAFE_RUN_ID.fullmatch(run_id):
        raise SchemaSyncPullRequestError(
            "run_id must contain only letters, numbers, dot, underscore, or hyphen"
        )
    return f"automation/schema-sync-{run_id}"


def requires_schema_sync_publication(report: ScheduledSchemaSyncReport) -> bool:
    """Return whether the validated core report requires a Git commit and PR update."""
    return report.outcome in {
        SchemaSyncOutcome.CHANGED,
        SchemaSyncOutcome.MANUAL_CLEANUP_REQUIRED,
    }


def build_cumulative_schema_sync_report(
    *,
    latest: ScheduledSchemaSyncReport,
    baseline: Mapping[str, DatabaseSchema],
    current: Mapping[str, DatabaseSchema],
    cumulative_changed_paths: Sequence[str],
) -> ScheduledSchemaSyncReport:
    """Recompute table impact against main so an updated PR body stays cumulative."""
    raw_paths = tuple(sorted(set(cumulative_changed_paths)))
    databases = []
    for database in latest.databases:
        before = baseline[database.key]
        after = current[database.key]
        summary = summarize_schema_change(before, after, database.key)
        prefix = f"catalog/{database.key}/generated/raw/"
        databases.append(
            DatabaseSchemaSyncReport(
                key=database.key,
                clickhouse_database=database.clickhouse_database,
                added=summary.added,
                modified=summary.modified,
                deleted=summary.deleted,
                raw_changed_paths=tuple(path for path in raw_paths if path.startswith(prefix)),
                review_paths=summary.review_files,
            )
        )
    if not any(database.has_changes for database in databases):
        raise SchemaSyncPullRequestError(
            "schema-sync commit has no cumulative technical schema change against main"
        )
    outcome = (
        SchemaSyncOutcome.MANUAL_CLEANUP_REQUIRED
        if latest.manual_cleanup
        else SchemaSyncOutcome.CHANGED
    )
    return ScheduledSchemaSyncReport(
        run_id=latest.run_id,
        outcome=outcome,
        databases=tuple(databases),
        warnings=latest.warnings,
        manual_cleanup=latest.manual_cleanup,
    )
