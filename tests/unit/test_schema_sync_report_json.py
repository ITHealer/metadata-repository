"""Tests for stable scheduled-sync artifacts consumed by later PR automation."""

import json
from pathlib import Path

from metadata_pipeline.domain.schema_sync import (
    DatabaseSchemaSyncReport,
    ScheduledSchemaSyncReport,
    SchemaSyncOutcome,
)
from metadata_pipeline.io.schema_sync_report_json import (
    write_schema_sync_pr_body,
    write_schema_sync_report,
)


def test_report_and_pr_body_are_deterministic_and_omit_secrets(tmp_path: Path) -> None:
    report = ScheduledSchemaSyncReport(
        run_id="20260721-010203",
        outcome=SchemaSyncOutcome.MANUAL_CLEANUP_REQUIRED,
        databases=(
            DatabaseSchemaSyncReport(
                key="alpha",
                clickhouse_database="Alpha",
                modified=("customers",),
                raw_changed_paths=("catalog/alpha/generated/raw/schema.json",),
                review_paths=("catalog/alpha/review/customers.yml",),
            ),
        ),
        manual_cleanup=("alpha.customers:orphaned_review_column:legacy",),
    )
    report_path = tmp_path / "report.json"
    pr_body_path = tmp_path / "pr-body.md"

    assert write_schema_sync_report(report_path, report) is True
    assert write_schema_sync_pr_body(pr_body_path, report) is True
    assert write_schema_sync_report(report_path, report) is False
    assert write_schema_sync_pr_body(pr_body_path, report) is False

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["format_version"] == "schema-sync-report-v1"
    assert payload["databases"][0]["modified"] == ["customers"]
    body = pr_body_path.read_text(encoding="utf-8")
    assert "| `alpha` | None | `customers` | None |" in body
    assert "`catalog/alpha/review/customers.yml`" in body
    assert "orphaned_review_column:legacy" in body
    assert "clickhouse://" not in report_path.read_text(encoding="utf-8") + body
