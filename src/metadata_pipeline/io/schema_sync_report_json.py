"""Stable JSON and Markdown output for scheduled schema synchronization."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from metadata_pipeline.domain.schema_sync import ScheduledSchemaSyncReport
from metadata_pipeline.io.atomic_text import write_text_if_changed


class SchemaSyncReportError(ValueError):
    """Raised when a persisted scheduled-sync report is missing or invalid."""


def load_schema_sync_report(path: Path) -> ScheduledSchemaSyncReport:
    """Load the strict report contract consumed by PR automation."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return ScheduledSchemaSyncReport.model_validate(payload)
    except (FileNotFoundError, OSError, json.JSONDecodeError, ValidationError) as error:
        raise SchemaSyncReportError(f"unable to load schema-sync report {path}: {error}") from error


def write_schema_sync_report(path: Path, report: ScheduledSchemaSyncReport) -> bool:
    """Write a deterministic, non-secret JSON report."""
    content = json.dumps(
        report.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    return write_text_if_changed(path, content + "\n")


def write_schema_sync_pr_body(path: Path, report: ScheduledSchemaSyncReport) -> bool:
    """Write a compact multi-database Draft PR description."""
    lines = [
        "## Automated ClickHouse schema sync",
        "",
        "A domain reviewer must resolve every affected reviewer YAML before approval.",
        "",
        "| Database | Added | Modified | Deleted |",
        "|---|---|---|---|",
    ]
    for database in report.databases:
        if not database.has_changes:
            continue
        lines.append(
            f"| `{database.key}` | {_display(database.added)} | "
            f"{_display(database.modified)} | {_display(database.deleted)} |"
        )
    lines.extend(("", "## Reviewer attention", ""))
    review_paths = sorted({path for database in report.databases for path in database.review_paths})
    lines.extend(f"- `{review_path}`" for review_path in review_paths)
    if not review_paths:
        lines.append("- No reviewer file requires changes.")
    if report.manual_cleanup:
        lines.extend(("", "## Manual cleanup required", ""))
        lines.extend(f"- `{item}`" for item in report.manual_cleanup)
    lines.extend(
        (
            "",
            "Run `make review-validate` after resolving reviewer-owned metadata.",
            "",
        )
    )
    return write_text_if_changed(path, "\n".join(lines))


def _display(values: tuple[str, ...]) -> str:
    return ", ".join(f"`{value}`" for value in values) if values else "None"
