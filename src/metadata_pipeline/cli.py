"""Command-line entrypoint for the metadata pipeline."""

from __future__ import annotations

import argparse
import json
import platform
import sys
from collections.abc import Sequence
from pathlib import Path

from metadata_pipeline import __version__
from metadata_pipeline.adapters.generator.deterministic import DeterministicDocumentGenerator
from metadata_pipeline.adapters.generator.openai_compatible import (
    GatewayConfigurationError,
    OpenAICompatibleDocumentGenerator,
    OpenAICompatibleSettings,
)
from metadata_pipeline.adapters.git.changed_paths import (
    GitDiffError,
    read_changed_paths,
    read_commit_changes,
)
from metadata_pipeline.adapters.index.manifest import ManifestIndexStore
from metadata_pipeline.adapters.schema.tbls_json import TblsSchemaSource
from metadata_pipeline.application.catalog import (
    CatalogConfigurationError,
    CatalogContext,
    discover_database_keys,
    load_catalog_context,
    validate_database_scope,
)
from metadata_pipeline.application.classify_changes import classify_changed_paths
from metadata_pipeline.application.create_drafts import (
    DraftAction,
    DraftGenerationError,
    create_review_drafts,
)
from metadata_pipeline.application.index_changes import map_index_actions, reconcile_index
from metadata_pipeline.application.publish_metadata import (
    PublicationPreflightError,
    prepare_chunk_artifact,
    prepare_publication,
    publish_batch,
    validate_published_directory,
    write_chunk_artifact,
)
from metadata_pipeline.application.review_contract import (
    export_review_json_schema,
    validate_review_directory,
)
from metadata_pipeline.application.schema_sync_summary import (
    render_schema_sync_pr_body,
    summarize_schema_change,
)
from metadata_pipeline.io.atomic_text import write_text_if_changed
from metadata_pipeline.io.chunk_jsonl import load_chunks
from metadata_pipeline.io.review_yaml import ReviewFileError
from metadata_pipeline.ports.index_store import IndexStoreError
from metadata_pipeline.ports.schema_source import SchemaSourceError
from metadata_pipeline.validation.review import IssueSeverity, ValidationIssue

MINIMUM_PYTHON = (3, 9)


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level command parser."""
    parser = argparse.ArgumentParser(
        prog="metadata",
        description="Manage the ClickHouse metadata review pipeline.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    commands = parser.add_subparsers(dest="command")
    commands.add_parser(
        "doctor",
        help="Check whether the local runtime meets project requirements.",
    )
    catalog_check = commands.add_parser(
        "catalog-check",
        help="Validate one database profile, tbls config, and raw schema allowlist.",
    )
    _add_database_context(catalog_check)
    catalog_check.add_argument("--schema", type=Path)
    catalog_check_all = commands.add_parser(
        "catalog-check-all",
        help="Validate every configured database profile.",
    )
    catalog_check_all.add_argument("--repository-root", type=Path, default=Path("."))
    export_schema = commands.add_parser(
        "export-review-schema",
        help="Generate JSON Schema from the Pydantic reviewer contract.",
    )
    export_schema.add_argument(
        "--output",
        type=Path,
        default=Path("contracts/reviewer_metadata.schema.json"),
    )
    draft = commands.add_parser(
        "draft",
        help="Create or refresh deterministic reviewer YAML drafts.",
    )
    _add_review_paths(draft)
    validate_review = commands.add_parser(
        "validate-review",
        help="Validate reviewer metadata against raw tbls schema.json.",
    )
    _add_review_paths(validate_review)
    publish = commands.add_parser(
        "publish",
        help="Merge raw and reviewer metadata into generated Markdown.",
    )
    _add_publication_paths(publish)
    _add_generator_arguments(publish)
    publish.add_argument("--chunk-output", type=Path)
    publish.add_argument(
        "--table",
        action="append",
        dest="tables",
        default=[],
        help="Publish only this table; repeat the option to select multiple tables.",
    )
    validate_published = commands.add_parser(
        "validate-published",
        help="Require committed published Markdown to match deterministic sources.",
    )
    _add_publication_paths(validate_published)
    chunk = commands.add_parser(
        "chunk",
        help="Build a validated semantic chunk JSONL dry-run artifact.",
    )
    _add_publication_paths(chunk)
    _add_generator_arguments(chunk)
    chunk.add_argument("--dry-run", action="store_true", required=True)
    chunk.add_argument(
        "--output",
        type=Path,
    )
    classify = commands.add_parser(
        "classify-changes",
        help="Classify PR and latest-commit paths for metadata CI.",
    )
    classify.add_argument("--base", required=True)
    classify.add_argument("--head", required=True)
    classify.add_argument("--github-output", type=Path)
    schema_sync_summary = commands.add_parser(
        "schema-sync-summary",
        help="Compare two tbls schema files and render a draft PR body.",
    )
    schema_sync_summary.add_argument("--before", type=Path, required=True)
    schema_sync_summary.add_argument("--after", type=Path, required=True)
    schema_sync_summary.add_argument("--output", type=Path, required=True)
    index_manifest = commands.add_parser(
        "index-manifest",
        help="Reconcile approved chunks into a versioned manifest and Git action report.",
    )
    index_manifest.add_argument("--chunks", type=Path, required=True)
    index_manifest.add_argument("--manifest", type=Path, required=True)
    index_manifest.add_argument("--source-commit", required=True)
    index_manifest.add_argument("--base", required=True)
    index_manifest.add_argument("--head", required=True)
    index_manifest.add_argument("--actions-output", type=Path, required=True)
    return parser


def _add_review_paths(parser: argparse.ArgumentParser) -> None:
    _add_database_context(parser)
    parser.add_argument(
        "--schema",
        type=Path,
    )
    parser.add_argument(
        "--review-dir",
        type=Path,
    )
    parser.add_argument(
        "--contract",
        type=Path,
    )


def _add_publication_paths(parser: argparse.ArgumentParser) -> None:
    _add_review_paths(parser)
    parser.add_argument(
        "--published-dir",
        type=Path,
    )
    parser.add_argument("--source-review-commit", required=True)


def _add_generator_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--mode", choices=("mock", "live"), default="mock")


def _add_database_context(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--database",
        default="commerce_demo",
        help="Lowercase repository database key configured under config/databases/.",
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path("."),
        help="Repository root used to resolve database-aware default paths.",
    )


def run_doctor() -> int:
    """Check the Python runtime and return a process-compatible status code."""
    current = sys.version_info[:2]
    supported = current >= MINIMUM_PYTHON
    status = "ok" if supported else "unsupported"
    minimum = ".".join(str(part) for part in MINIMUM_PYTHON)

    print(f"python={platform.python_version()} status={status} minimum={minimum}")
    return 0 if supported else 1


def run_catalog_check(context: CatalogContext, schema_path: Path) -> int:
    """Validate one database boundary and print a concise operator result."""
    try:
        validate_database_scope(context.profile, schema_path)
    except CatalogConfigurationError as error:
        print(f"catalog configuration error: {error}", file=sys.stderr)
        return 1
    print(
        f"catalog validation passed: {context.profile.key} ({len(context.profile.tables)} table(s))"
    )
    return 0


def run_catalog_check_all(repository_root: Path) -> int:
    """Validate all configured databases without stopping at the first profile."""
    database_keys = discover_database_keys(repository_root)
    if not database_keys:
        print("catalog configuration error: no database profiles found", file=sys.stderr)
        return 1
    failed = False
    for database in database_keys:
        context = _load_catalog_context(database, repository_root)
        if context is None:
            failed = True
            continue
        failed |= run_catalog_check(context, context.layout.schema_path) != 0
    return 1 if failed else 0


def run_validate_review(schema: Path, review_dir: Path, contract: Path) -> int:
    """Print actionable review issues and return a CI-compatible status."""
    issues = validate_review_directory(schema, review_dir, contract)
    for issue in issues:
        print(
            f"{issue.path}:{issue.field}: {issue.severity.value}: {issue.code}: {issue.message}",
            file=sys.stderr,
        )
    error_count = sum(issue.severity is IssueSeverity.ERROR for issue in issues)
    warning_count = len(issues) - error_count
    if error_count:
        print(
            f"review metadata validation failed: {error_count} error(s), "
            f"{warning_count} warning(s)",
            file=sys.stderr,
        )
        return 1
    print(f"review metadata validation passed: {review_dir} ({warning_count} warning(s))")
    return 0


def run_create_drafts(schema: Path, review_dir: Path, contract: Path) -> int:
    """Create drafts, format results, and fail when manual cleanup is required."""
    try:
        results = create_review_drafts(schema, review_dir, contract)
    except (DraftGenerationError, ReviewFileError, SchemaSourceError) as error:
        print(f"draft generation failed: {error}", file=sys.stderr)
        return 1

    requires_manual_review = False
    for result in results:
        details = f" ({', '.join(result.issue_codes)})" if result.issue_codes else ""
        print(f"{result.table}: {result.action.value}: {result.path}{details}")
        requires_manual_review |= result.action is DraftAction.REQUIRES_MANUAL_REVIEW
    if requires_manual_review:
        print("draft generation requires manual review", file=sys.stderr)
        return 1
    print(f"draft generation completed: {len(results)} table(s)")
    return 0


def run_publish(
    schema: Path,
    review_dir: Path,
    contract: Path,
    published_dir: Path,
    source_review_commit: str,
    mode: str,
    chunk_output: Path | None = None,
    tables: tuple[str, ...] = (),
) -> int:
    """Preflight and write generated Markdown with CI-compatible errors."""
    try:
        generator = _generator(mode)
        batch = prepare_publication(
            schema,
            review_dir,
            contract,
            published_dir,
            source_review_commit,
            generator,
            tables,
        )
        chunks = prepare_chunk_artifact(batch, chunk_output) if chunk_output else ()
        results = publish_batch(batch, published_dir, prune_orphans=not tables)
        chunk_changed = write_chunk_artifact(chunk_output, chunks) if chunk_output else False
    except (PublicationPreflightError, GatewayConfigurationError) as error:
        return _print_publication_error(error)
    for warning in batch.warnings:
        _print_issue(warning)
    for result in results:
        print(f"{result.action.value}: {result.path}")
    if chunk_output:
        state = "updated" if chunk_changed else "unchanged"
        print(f"chunk artifact {state}: {chunk_output} ({len(chunks)} chunk(s))")
    print(f"publication completed: {len(batch.items)} document(s)")
    return 0


def run_validate_published(
    schema: Path,
    review_dir: Path,
    contract: Path,
    published_dir: Path,
    source_review_commit: str,
) -> int:
    """Regenerate deterministic output in memory and compare committed bytes."""
    try:
        batch = prepare_publication(
            schema,
            review_dir,
            contract,
            published_dir,
            source_review_commit,
            DeterministicDocumentGenerator(),
        )
    except PublicationPreflightError as error:
        return _print_publication_error(error)
    issues = validate_published_directory(batch, published_dir)
    for issue in issues:
        _print_issue(issue)
    if issues:
        print(f"published validation failed: {len(issues)} issue(s)", file=sys.stderr)
        return 1
    print(f"published validation passed: {len(batch.items)} document(s)")
    return 0


def run_chunk(
    schema: Path,
    review_dir: Path,
    contract: Path,
    published_dir: Path,
    source_review_commit: str,
    mode: str,
    output: Path,
) -> int:
    """Prepare documents and write validated semantic chunks as JSONL."""
    try:
        batch = prepare_publication(
            schema,
            review_dir,
            contract,
            published_dir,
            source_review_commit,
            _generator(mode),
        )
        chunks = prepare_chunk_artifact(batch, output)
        changed = write_chunk_artifact(output, chunks)
    except (PublicationPreflightError, GatewayConfigurationError) as error:
        return _print_publication_error(error)
    state = "updated" if changed else "unchanged"
    print(f"chunk dry-run {state}: {output} ({len(chunks)} chunk(s))")
    return 0


def run_classify_changes(base: str, head: str, github_output: Path | None) -> int:
    """Classify PR-wide and latest-commit paths without embedding Git logic in CI YAML."""
    try:
        pr = classify_changed_paths(read_changed_paths(base, head))
        latest = classify_changed_paths(read_commit_changes(head))
    except GitDiffError as error:
        print(f"change classification failed: {error}", file=sys.stderr)
        return 1
    outputs = {**pr.github_outputs("pr_"), **latest.github_outputs("latest_")}
    if github_output is not None:
        github_output.parent.mkdir(parents=True, exist_ok=True)
        with github_output.open("a", encoding="utf-8", newline="\n") as stream:
            for key, value in sorted(outputs.items()):
                stream.write(f"{key}={value}\n")
    print(json.dumps(outputs, sort_keys=True))
    return 0


def run_schema_sync_summary(before: Path, after: Path, output: Path) -> int:
    """Write a deterministic table-level schema drift summary."""
    try:
        summary = summarize_schema_change(
            TblsSchemaSource(before).load(),
            TblsSchemaSource(after).load(),
        )
    except SchemaSourceError as error:
        print(f"schema sync summary failed: {error}", file=sys.stderr)
        return 1
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_schema_sync_pr_body(summary), encoding="utf-8")
    print(
        f"schema sync summary written: {output} "
        f"({len(summary.added)} added, {len(summary.modified)} modified, "
        f"{len(summary.deleted)} deleted)"
    )
    return 0


def run_index_manifest(
    chunks_path: Path,
    manifest_path: Path,
    source_commit: str,
    base: str,
    head: str,
    actions_output: Path,
) -> int:
    """Build a full approved manifest and report document actions from Git."""
    try:
        chunks = load_chunks(chunks_path)
        actions = map_index_actions(read_changed_paths(base, head))
        update = reconcile_index(ManifestIndexStore(manifest_path), chunks, source_commit)
    except (ValueError, GitDiffError, IndexStoreError) as error:
        print(f"index manifest failed: {error}", file=sys.stderr)
        return 1
    action_payload = [action.model_dump(mode="json") for action in actions]
    write_text_if_changed(
        actions_output,
        json.dumps(action_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    print(
        f"index manifest {'updated' if update.changed else 'unchanged'}: "
        f"{len(update.manifest.documents)} document(s), "
        f"{len(update.deleted_chunk_ids)} delete(s), "
        f"{len(update.upserted_chunk_ids)} upsert(s), {len(actions)} Git action(s)"
    )
    return 0


def _generator(mode: str) -> DeterministicDocumentGenerator | OpenAICompatibleDocumentGenerator:
    if mode == "live":
        return OpenAICompatibleDocumentGenerator.from_settings(OpenAICompatibleSettings.from_env())
    return DeterministicDocumentGenerator()


def _print_publication_error(
    error: PublicationPreflightError | GatewayConfigurationError,
) -> int:
    if isinstance(error, PublicationPreflightError):
        for issue in error.issues:
            _print_issue(issue)
    else:
        print(f"generator configuration error: {error}", file=sys.stderr)
    return 1


def _print_issue(issue: ValidationIssue) -> None:
    print(
        f"{issue.path}:{issue.field}: {issue.severity.value}: {issue.code}: {issue.message}",
        file=sys.stderr,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Execute the CLI and return an exit code without terminating the interpreter."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "doctor":
        return run_doctor()
    if args.command == "catalog-check-all":
        return run_catalog_check_all(args.repository_root)
    if args.command == "catalog-check":
        context = _load_catalog_context(args.database, args.repository_root)
        if context is None:
            return 1
        return run_catalog_check(context, args.schema or context.layout.schema_path)
    if args.command == "export-review-schema":
        export_review_json_schema(args.output)
        print(f"review JSON Schema written: {args.output}")
        return 0
    if args.command == "draft":
        resolved = _resolve_catalog_paths(args)
        if resolved is None:
            return 1
        context, schema, review_dir, contract, _ = resolved
        if run_catalog_check(context, schema):
            return 1
        return run_create_drafts(schema, review_dir, contract)
    if args.command == "validate-review":
        resolved = _resolve_catalog_paths(args)
        if resolved is None:
            return 1
        context, schema, review_dir, contract, _ = resolved
        if run_catalog_check(context, schema):
            return 1
        return run_validate_review(schema, review_dir, contract)
    if args.command == "publish":
        resolved = _resolve_catalog_paths(args)
        if resolved is None:
            return 1
        context, schema, review_dir, contract, published_dir = resolved
        if run_catalog_check(context, schema):
            return 1
        return run_publish(
            schema,
            review_dir,
            contract,
            published_dir,
            args.source_review_commit,
            args.mode,
            args.chunk_output,
            tuple(args.tables),
        )
    if args.command == "validate-published":
        resolved = _resolve_catalog_paths(args)
        if resolved is None:
            return 1
        context, schema, review_dir, contract, published_dir = resolved
        if run_catalog_check(context, schema):
            return 1
        return run_validate_published(
            schema,
            review_dir,
            contract,
            published_dir,
            args.source_review_commit,
        )
    if args.command == "chunk":
        resolved = _resolve_catalog_paths(args)
        if resolved is None:
            return 1
        context, schema, review_dir, contract, published_dir = resolved
        if run_catalog_check(context, schema):
            return 1
        return run_chunk(
            schema,
            review_dir,
            contract,
            published_dir,
            args.source_review_commit,
            args.mode,
            args.output or context.layout.chunk_output,
        )
    if args.command == "classify-changes":
        return run_classify_changes(args.base, args.head, args.github_output)
    if args.command == "schema-sync-summary":
        return run_schema_sync_summary(args.before, args.after, args.output)
    if args.command == "index-manifest":
        return run_index_manifest(
            args.chunks,
            args.manifest,
            args.source_commit,
            args.base,
            args.head,
            args.actions_output,
        )

    parser.print_help()
    return 0


def _load_catalog_context(database: str, repository_root: Path) -> CatalogContext | None:
    try:
        return load_catalog_context(database, repository_root)
    except (CatalogConfigurationError, ValueError) as error:
        print(f"catalog configuration error: {error}", file=sys.stderr)
        return None


def _resolve_catalog_paths(
    args: argparse.Namespace,
) -> tuple[CatalogContext, Path, Path, Path, Path] | None:
    """Resolve optional CLI path overrides against one validated database layout."""
    context = _load_catalog_context(args.database, args.repository_root)
    if context is None:
        return None
    root = context.layout.repository_root
    return (
        context,
        args.schema or context.layout.schema_path,
        args.review_dir or context.layout.review_dir,
        args.contract or root / "contracts" / "metadata_contract.yml",
        getattr(args, "published_dir", None) or context.layout.published_dir,
    )


def entrypoint() -> None:
    """Console-script adapter."""
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
