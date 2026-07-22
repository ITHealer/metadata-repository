"""Preflight-first orchestration for scheduled multi-database schema sync."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from metadata_pipeline.adapters.schema.tbls_json import TblsSchemaSource
from metadata_pipeline.application.catalog import (
    CatalogContext,
    discover_scheduled_database_keys,
    load_catalog_context,
    validate_database_scope,
)
from metadata_pipeline.application.create_drafts import (
    DraftAction,
    DraftResult,
    create_review_drafts,
)
from metadata_pipeline.application.schema_sync_summary import (
    SchemaSyncSummary,
    summarize_schema_change,
)
from metadata_pipeline.domain.schema_sync import (
    DatabaseSchemaSyncReport,
    ScheduledSchemaSyncReport,
    SchemaSyncOutcome,
)
from metadata_pipeline.io.atomic_bytes import write_bytes_if_changed
from metadata_pipeline.io.schema_sync_settings import SchemaSyncSettings
from metadata_pipeline.ports.schema_documenter import SchemaDocumenter
from metadata_pipeline.ports.schema_source import DatabaseSchema

_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class ScheduledSchemaSyncError(ValueError):
    """Raised before a bot commit when staged sync cannot complete safely."""


@dataclass(frozen=True)
class _StagedDatabase:
    """One generated and validated database snapshot waiting for draft refresh."""

    context: CatalogContext
    staged_raw_dir: Path
    summary: SchemaSyncSummary
    raw_changed_paths: tuple[str, ...]


@dataclass(frozen=True)
class _PreparedDatabase:
    """One fully generated and draft-refreshed database waiting for publication."""

    context: CatalogContext
    staged_raw_dir: Path
    staged_review_dir: Path
    summary: SchemaSyncSummary
    raw_changed_paths: tuple[str, ...]
    draft_results: tuple[DraftResult, ...]


def synchronize_scheduled_schemas(
    *,
    repository_root: Path,
    staging_root: Path,
    run_id: str,
    settings: SchemaSyncSettings,
    documenter: SchemaDocumenter,
) -> ScheduledSchemaSyncReport:
    """Stage every scheduled database, then publish all validated changes together."""
    if not settings.enabled:
        return ScheduledSchemaSyncReport(
            run_id=run_id,
            outcome=SchemaSyncOutcome.DISABLED,
        )

    root = repository_root.resolve()
    database_keys = discover_scheduled_database_keys(root)
    if not database_keys:
        return ScheduledSchemaSyncReport(
            run_id=run_id,
            outcome=SchemaSyncOutcome.NOOP,
            warnings=("no enabled database profile opted in to scheduled sync",),
        )

    contexts = tuple(load_catalog_context(database, root) for database in database_keys)
    dsns = {context.profile.key: settings.dsn_for(context.profile) for context in contexts}
    run_dir = _reset_run_directory(root, staging_root.resolve(), run_id)
    staged = tuple(
        _stage_database(
            context,
            root,
            run_dir,
            dsns[context.profile.key],
            documenter,
        )
        for context in contexts
    )
    prepared = tuple(_prepare_review(item, root, run_dir) for item in staged)
    changed = tuple(item for item in prepared if item.summary.has_changes)
    warnings = tuple(
        sorted(
            f"{item.context.profile.key}: raw bytes changed outside the supported schema contract; "
            "catalog was left unchanged"
            for item in prepared
            if item.raw_changed_paths and not item.summary.has_changes
        )
    )
    if not changed:
        return ScheduledSchemaSyncReport(
            run_id=run_id,
            outcome=SchemaSyncOutcome.NOOP,
            databases=tuple(_database_report(item) for item in prepared),
            warnings=warnings,
        )

    # All external generation, parsing, scope checks, and draft refreshes succeeded above.
    # Only now may generated raw and reviewer draft bytes enter the working catalog.
    for item in changed:
        _sync_directory(
            item.staged_raw_dir,
            item.context.layout.raw_dir,
            remove_orphans=True,
        )
        _sync_directory(
            item.staged_review_dir,
            item.context.layout.review_dir,
            remove_orphans=False,
        )

    manual_cleanup = tuple(
        sorted(
            f"{item.context.profile.key}.{result.table}:{issue}"
            for item in changed
            for result in item.draft_results
            if result.action is DraftAction.REQUIRES_MANUAL_REVIEW
            for issue in result.issue_codes
        )
    )
    outcome = (
        SchemaSyncOutcome.MANUAL_CLEANUP_REQUIRED if manual_cleanup else SchemaSyncOutcome.CHANGED
    )
    return ScheduledSchemaSyncReport(
        run_id=run_id,
        outcome=outcome,
        databases=tuple(_database_report(item) for item in prepared),
        warnings=warnings,
        manual_cleanup=manual_cleanup,
    )


def _stage_database(
    context: CatalogContext,
    repository_root: Path,
    run_dir: Path,
    dsn: str,
    documenter: SchemaDocumenter,
) -> _StagedDatabase:
    """Generate, validate, and compare raw output without touching catalog outputs."""
    database_dir = run_dir / context.profile.key
    staged_raw_dir = database_dir / "raw"
    documenter.generate(
        profile=context.profile,
        config_path=context.layout.tbls_config_path,
        output_dir=staged_raw_dir,
        dsn=dsn,
    )
    staged_schema_path = staged_raw_dir / "schema.json"
    # Missing allowlisted tables are valid deletion candidates for reviewer cleanup.
    # Unexpected tables remain a hard scope violation.
    validate_database_scope(
        context.profile,
        staged_schema_path,
        allow_missing_tables=True,
    )
    after = TblsSchemaSource(staged_schema_path).load()
    before = _load_committed_or_empty_schema(context)
    summary = summarize_schema_change(before, after, context.profile.key)
    raw_changed_paths = _changed_paths(
        staged_raw_dir,
        context.layout.raw_dir,
        repository_root,
    )

    return _StagedDatabase(
        context=context,
        staged_raw_dir=staged_raw_dir,
        summary=summary,
        raw_changed_paths=raw_changed_paths,
    )


def _prepare_review(
    staged: _StagedDatabase,
    repository_root: Path,
    run_dir: Path,
) -> _PreparedDatabase:
    """Refresh reviewer drafts only after every raw database preflight has succeeded."""
    staged_review_dir = run_dir / staged.context.profile.key / "review"
    draft_results: tuple[DraftResult, ...] = ()
    if staged.summary.has_changes:
        _copy_review_inputs(staged.context.layout.review_dir, staged_review_dir)
        draft_results = create_review_drafts(
            staged.staged_raw_dir / "schema.json",
            staged_review_dir,
            repository_root / "contracts" / "metadata_contract.yml",
            schema_reference=_repository_path(
                staged.context.layout.schema_path,
                repository_root,
            ),
        )
    return _PreparedDatabase(
        context=staged.context,
        staged_raw_dir=staged.staged_raw_dir,
        staged_review_dir=staged_review_dir,
        summary=staged.summary,
        raw_changed_paths=staged.raw_changed_paths,
        draft_results=draft_results,
    )


def _load_committed_or_empty_schema(context: CatalogContext) -> DatabaseSchema:
    if context.layout.schema_path.is_file():
        return TblsSchemaSource(context.layout.schema_path).load()
    return DatabaseSchema(
        name=context.profile.clickhouse_database,
        description="",
        tables=(),
        relations=(),
    )


def _copy_review_inputs(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, destination, dirs_exist_ok=True)


def _database_report(item: _PreparedDatabase) -> DatabaseSchemaSyncReport:
    return DatabaseSchemaSyncReport(
        key=item.context.profile.key,
        clickhouse_database=item.context.profile.clickhouse_database,
        added=item.summary.added,
        modified=item.summary.modified,
        deleted=item.summary.deleted,
        raw_changed_paths=(item.raw_changed_paths if item.summary.has_changes else ()),
        review_paths=item.summary.review_files,
    )


def _reset_run_directory(repository_root: Path, staging_root: Path, run_id: str) -> Path:
    allowed_root = (repository_root / "build" / "schema-sync").resolve()
    try:
        staging_root.relative_to(allowed_root)
    except ValueError as error:
        raise ScheduledSchemaSyncError(f"staging_root must be inside {allowed_root}") from error
    if not _SAFE_RUN_ID.fullmatch(run_id):
        raise ScheduledSchemaSyncError(
            "run_id must contain only letters, numbers, dot, underscore, or hyphen"
        )
    run_dir = (staging_root / run_id).resolve()
    try:
        run_dir.relative_to(staging_root)
    except ValueError as error:
        raise ScheduledSchemaSyncError("staging run directory escaped staging root") from error
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    return run_dir


def _changed_paths(source: Path, destination: Path, repository_root: Path) -> tuple[str, ...]:
    source_files = _regular_files(source)
    destination_files = _regular_files(destination) if destination.is_dir() else {}
    changed = []
    for relative_path, source_path in source_files.items():
        destination_path = destination / relative_path
        if (
            relative_path not in destination_files
            or source_path.read_bytes() != destination_path.read_bytes()
        ):
            changed.append(_repository_path(destination_path, repository_root))
    for relative_path, destination_path in destination_files.items():
        if relative_path not in source_files:
            changed.append(_repository_path(destination_path, repository_root))
    return tuple(sorted(changed))


def _sync_directory(source: Path, destination: Path, *, remove_orphans: bool) -> None:
    source_files = _regular_files(source)
    destination_files = _regular_files(destination) if destination.is_dir() else {}
    for relative_path, source_path in source_files.items():
        write_bytes_if_changed(destination / relative_path, source_path.read_bytes())
    if remove_orphans:
        for relative_path, destination_path in destination_files.items():
            if relative_path not in source_files:
                destination_path.unlink()


def _regular_files(root: Path) -> dict[Path, Path]:
    if not root.is_dir():
        return {}
    files: dict[Path, Path] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ScheduledSchemaSyncError(f"staging/catalog symlinks are not supported: {path}")
        if path.is_file():
            files[path.relative_to(root)] = path
    return files


def _repository_path(path: Path, repository_root: Path) -> str:
    try:
        return path.resolve().relative_to(repository_root.resolve()).as_posix()
    except ValueError as error:
        raise ScheduledSchemaSyncError(f"path is outside repository root: {path}") from error
