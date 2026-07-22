"""Tests for provider-neutral single-active-PR decisions."""

from dataclasses import replace

import pytest

from metadata_pipeline.application.schema_sync_pr import (
    SchemaSyncPullRequestError,
    build_cumulative_schema_sync_report,
    requires_schema_sync_publication,
    resolve_active_schema_sync_pull_request,
    schema_sync_branch_name,
    validate_schema_sync_changed_paths,
)
from metadata_pipeline.domain.schema_sync import (
    DatabaseSchemaSyncReport,
    ScheduledSchemaSyncReport,
    SchemaSyncOutcome,
)
from metadata_pipeline.domain.schema_sync_pr import SchemaSyncPullRequest
from metadata_pipeline.ports.schema_source import ColumnSchema, DatabaseSchema, TableSchema


def _pull_request(number: int) -> SchemaSyncPullRequest:
    return SchemaSyncPullRequest(
        number=number,
        url=f"https://github.example/pr/{number}",
        head_ref=f"automation/schema-sync-run-{number}",
        is_draft=True,
    )


def _schema(*, column_type: str = "String") -> DatabaseSchema:
    return DatabaseSchema(
        name="alpha",
        description="",
        tables=(
            TableSchema(
                name="events",
                table_type="BASE TABLE",
                comment="Events",
                columns=(ColumnSchema("event_id", column_type, False, "Event ID"),),
            ),
        ),
        relations=(),
    )


def test_resolves_zero_or_one_active_pr_and_rejects_multiple() -> None:
    first = _pull_request(10)
    second = _pull_request(11)

    assert resolve_active_schema_sync_pull_request(()) is None
    assert resolve_active_schema_sync_pull_request((first,)) == first
    with pytest.raises(SchemaSyncPullRequestError, match="10, 11"):
        resolve_active_schema_sync_pull_request((first, second))


def test_commit_allowlist_rejects_every_unrelated_path() -> None:
    allowed = validate_schema_sync_changed_paths(
        (
            "catalog/alpha/review/events.yml",
            "catalog/alpha/generated/raw/schema.json",
        )
    )

    assert allowed == (
        "catalog/alpha/generated/raw/schema.json",
        "catalog/alpha/review/events.yml",
    )
    with pytest.raises(SchemaSyncPullRequestError, match="README.md"):
        validate_schema_sync_changed_paths(("catalog/alpha/review/events.yml", "README.md"))


def test_branch_name_and_publication_decision_follow_validated_report() -> None:
    assert schema_sync_branch_name("123-2") == "automation/schema-sync-123-2"
    with pytest.raises(SchemaSyncPullRequestError, match="run_id"):
        schema_sync_branch_name("../unsafe")
    assert not requires_schema_sync_publication(
        ScheduledSchemaSyncReport(run_id="run", outcome=SchemaSyncOutcome.NOOP)
    )
    assert requires_schema_sync_publication(
        ScheduledSchemaSyncReport(
            run_id="run",
            outcome=SchemaSyncOutcome.CHANGED,
            databases=(
                DatabaseSchemaSyncReport(
                    key="alpha",
                    clickhouse_database="alpha",
                    modified=("events",),
                ),
            ),
        )
    )


def test_cumulative_report_is_recomputed_against_main() -> None:
    before = _schema()
    after = replace(before, tables=(replace(before.tables[0], comment="Changed events"),))
    latest = ScheduledSchemaSyncReport(
        run_id="run-2",
        outcome=SchemaSyncOutcome.CHANGED,
        databases=(
            DatabaseSchemaSyncReport(
                key="alpha",
                clickhouse_database="alpha",
                modified=("events",),
            ),
        ),
    )

    cumulative = build_cumulative_schema_sync_report(
        latest=latest,
        baseline={"alpha": before},
        current={"alpha": after},
        cumulative_changed_paths=(
            "catalog/alpha/review/events.yml",
            "catalog/alpha/generated/raw/schema.json",
        ),
    )

    assert cumulative.databases[0].modified == ("events",)
    assert cumulative.databases[0].raw_changed_paths == ("catalog/alpha/generated/raw/schema.json",)
    assert cumulative.databases[0].review_paths == ("catalog/alpha/review/events.yml",)
