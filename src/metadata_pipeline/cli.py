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
from metadata_pipeline.adapters.schema.tbls_json import TblsSchemaSource
from metadata_pipeline.application.classify_changes import classify_changed_paths
from metadata_pipeline.application.create_drafts import (
    DraftAction,
    DraftGenerationError,
    create_review_drafts,
)
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
from metadata_pipeline.io.review_yaml import ReviewFileError
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
    export_schema = commands.add_parser(
        "export-review-schema",
        help="Generate JSON Schema from the Pydantic reviewer contract.",
    )
    export_schema.add_argument(
        "--output",
        type=Path,
        default=Path("schemas/reviewer_metadata.schema.json"),
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
        default=Path("build/chunks/commerce_demo.jsonl"),
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
    return parser


def _add_review_paths(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path("schema/raw/commerce_demo/schema.json"),
    )
    parser.add_argument(
        "--review-dir",
        type=Path,
        default=Path("metadata/review/commerce_demo"),
    )
    parser.add_argument(
        "--contract",
        type=Path,
        default=Path("config/metadata_contract.yml"),
    )


def _add_publication_paths(parser: argparse.ArgumentParser) -> None:
    _add_review_paths(parser)
    parser.add_argument(
        "--published-dir",
        type=Path,
        default=Path("knowledge/published/commerce_demo"),
    )
    parser.add_argument("--source-review-commit", required=True)


def _add_generator_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--mode", choices=("mock", "live"), default="mock")


def run_doctor() -> int:
    """Check the Python runtime and return a process-compatible status code."""
    current = sys.version_info[:2]
    supported = current >= MINIMUM_PYTHON
    status = "ok" if supported else "unsupported"
    minimum = ".".join(str(part) for part in MINIMUM_PYTHON)

    print(f"python={platform.python_version()} status={status} minimum={minimum}")
    return 0 if supported else 1


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
        )
        results = publish_batch(batch, published_dir)
    except (PublicationPreflightError, GatewayConfigurationError) as error:
        return _print_publication_error(error)
    for warning in batch.warnings:
        _print_issue(warning)
    for result in results:
        print(f"{result.action.value}: {result.path}")
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
    if args.command == "export-review-schema":
        export_review_json_schema(args.output)
        print(f"review JSON Schema written: {args.output}")
        return 0
    if args.command == "draft":
        return run_create_drafts(args.schema, args.review_dir, args.contract)
    if args.command == "validate-review":
        return run_validate_review(args.schema, args.review_dir, args.contract)
    if args.command == "publish":
        return run_publish(
            args.schema,
            args.review_dir,
            args.contract,
            args.published_dir,
            args.source_review_commit,
            args.mode,
        )
    if args.command == "validate-published":
        return run_validate_published(
            args.schema,
            args.review_dir,
            args.contract,
            args.published_dir,
            args.source_review_commit,
        )
    if args.command == "chunk":
        return run_chunk(
            args.schema,
            args.review_dir,
            args.contract,
            args.published_dir,
            args.source_review_commit,
            args.mode,
            args.output,
        )
    if args.command == "classify-changes":
        return run_classify_changes(args.base, args.head, args.github_output)
    if args.command == "schema-sync-summary":
        return run_schema_sync_summary(args.before, args.after, args.output)

    parser.print_help()
    return 0


def entrypoint() -> None:
    """Console-script adapter."""
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
