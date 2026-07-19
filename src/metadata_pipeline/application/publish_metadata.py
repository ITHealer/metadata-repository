"""Preflight-first orchestration for published metadata generation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from metadata_pipeline.adapters.schema.tbls_json import TblsSchemaSource
from metadata_pipeline.application.build_chunks import build_chunks
from metadata_pipeline.application.review_contract import validate_review_directory
from metadata_pipeline.domain.published import Chunk, PublishedDocument
from metadata_pipeline.io.chunk_jsonl import write_chunks
from metadata_pipeline.io.published_markdown import (
    render_published_document,
    write_published_document,
)
from metadata_pipeline.io.review_yaml import (
    ReviewFileError,
    load_review_contract,
    load_review_document,
)
from metadata_pipeline.ports.document_generator import (
    DocumentGenerationError,
    DocumentGenerator,
    PublicationContext,
)
from metadata_pipeline.ports.schema_source import SchemaSourceError
from metadata_pipeline.validation.chunks import validate_chunks
from metadata_pipeline.validation.published import validate_published_document
from metadata_pipeline.validation.review import IssueSeverity, ValidationIssue


class PublishAction(str, Enum):
    """Filesystem result for one published document."""

    CREATED = "created"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    DELETED = "deleted"


@dataclass(frozen=True)
class PreparedPublication:
    """One fully validated document ready for deterministic I/O."""

    review_path: Path
    output_path: Path
    context: PublicationContext
    document: PublishedDocument
    markdown: str


@dataclass(frozen=True)
class PublicationBatch:
    """All-or-nothing preflight result for one database."""

    items: tuple[PreparedPublication, ...]
    warnings: tuple[ValidationIssue, ...]


@dataclass(frozen=True)
class PublishResult:
    """Observable write/delete action formatted later by the CLI."""

    path: Path
    action: PublishAction


class PublicationPreflightError(ValueError):
    """Raised before writes when any source or generated document is invalid."""

    def __init__(self, issues: tuple[ValidationIssue, ...]) -> None:
        super().__init__(f"publication preflight failed with {len(issues)} issue(s)")
        self.issues = issues


def prepare_publication(
    schema_path: Path,
    review_dir: Path,
    contract_path: Path,
    output_dir: Path,
    source_review_commit: str,
    generator: DocumentGenerator,
) -> PublicationBatch:
    """Validate every input and generated model before any output file is written."""
    review_issues = validate_review_directory(schema_path, review_dir, contract_path)
    blockers = tuple(
        issue
        for issue in review_issues
        if issue.severity is IssueSeverity.ERROR or issue.code == "conflicting_evidence"
    )
    if blockers:
        raise PublicationPreflightError(blockers)
    warnings = tuple(issue for issue in review_issues if issue.severity is IssueSeverity.WARNING)

    try:
        schema = TblsSchemaSource(schema_path).load()
        contract = load_review_contract(contract_path)
        review_paths = sorted((*review_dir.glob("*.yml"), *review_dir.glob("*.yaml")))
        reviews = tuple((path, load_review_document(path)) for path in review_paths)
    except SchemaSourceError as error:
        raise PublicationPreflightError(
            (ValidationIssue("invalid_schema_source", schema_path, "$", str(error)),)
        ) from error
    except ReviewFileError as error:
        raise PublicationPreflightError(
            tuple(
                ValidationIssue("invalid_review_document", error.path, issue.field, issue.message)
                for issue in error.issues
            )
        ) from error

    if not reviews:
        raise PublicationPreflightError(
            (
                ValidationIssue(
                    "missing_review_files",
                    review_dir,
                    "$",
                    "no reviewer YAML documents found",
                ),
            )
        )
    tables = {table.name: table for table in schema.tables}
    prepared: list[PreparedPublication] = []
    generated_issues: list[ValidationIssue] = []
    for review_path, review in reviews:
        table = tables[review.table]
        context = PublicationContext(
            schema=schema,
            table=table,
            review=review,
            source_schema_path=_stable_path(schema_path, schema.name, "schema.json"),
            source_review_path=_stable_path(review_path, schema.name, review_path.name),
            source_review_commit=source_review_commit,
        )
        output_path = output_dir / f"{review.table}.md"
        try:
            document = generator.generate(context)
        except (DocumentGenerationError, ValueError) as error:
            generated_issues.append(
                ValidationIssue(
                    "document_generation_failed",
                    review_path,
                    "$",
                    str(error),
                )
            )
            continue
        issues = validate_published_document(context, document, output_path)
        generated_issues.extend(issues)
        if issues:
            continue
        prepared.append(
            PreparedPublication(
                review_path=review_path,
                output_path=output_path,
                context=context,
                document=document,
                markdown=render_published_document(document),
            )
        )

    if generated_issues:
        raise PublicationPreflightError(tuple(generated_issues))
    if any(item.document.contract_version != contract.contract_version for item in prepared):
        raise PublicationPreflightError(
            (
                ValidationIssue(
                    "published_contract_version_mismatch",
                    contract_path,
                    "contract_version",
                    "generated document does not use the canonical contract version",
                ),
            )
        )
    return PublicationBatch(tuple(prepared), warnings)


def publish_batch(batch: PublicationBatch, output_dir: Path) -> tuple[PublishResult, ...]:
    """Write a preflighted batch and remove generated-only orphan Markdown files."""
    results: list[PublishResult] = []
    expected_paths = {item.output_path for item in batch.items}
    existing_paths = set(output_dir.glob("*.md")) if output_dir.exists() else set()
    for item in batch.items:
        existed = item.output_path.exists()
        changed = write_published_document(item.output_path, item.document)
        action = PublishAction.UNCHANGED
        if changed:
            action = PublishAction.UPDATED if existed else PublishAction.CREATED
        results.append(PublishResult(item.output_path, action))
    for orphan in sorted(existing_paths - expected_paths):
        orphan.unlink()
        results.append(PublishResult(orphan, PublishAction.DELETED))
    return tuple(results)


def validate_published_directory(
    batch: PublicationBatch,
    output_dir: Path,
) -> tuple[ValidationIssue, ...]:
    """Compare committed Markdown bytes with freshly prepared deterministic output."""
    issues: list[ValidationIssue] = []
    expected_paths = {item.output_path for item in batch.items}
    for item in batch.items:
        try:
            actual = item.output_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            issues.append(
                ValidationIssue(
                    "missing_published_document",
                    item.output_path,
                    "$",
                    "published document is missing; run metadata publish",
                )
            )
            continue
        if actual != item.markdown:
            issues.append(
                ValidationIssue(
                    "stale_published_document",
                    item.output_path,
                    "$",
                    "published document differs from validated sources; regenerate it",
                )
            )
    existing_paths = set(output_dir.glob("*.md")) if output_dir.exists() else set()
    for orphan in sorted(existing_paths - expected_paths):
        issues.append(
            ValidationIssue(
                "orphaned_published_document",
                orphan,
                "$",
                "published file has no matching reviewer document",
            )
        )
    return tuple(issues)


def prepare_chunk_artifact(
    batch: PublicationBatch,
    output_path: Path,
) -> tuple[Chunk, ...]:
    """Build and validate all chunks before JSONL output."""
    chunks: list[Chunk] = []
    issues: list[ValidationIssue] = []
    for item in batch.items:
        document_chunks = build_chunks(item.document)
        issues.extend(validate_chunks(item.document, document_chunks, output_path))
        chunks.extend(document_chunks)
    if issues:
        raise PublicationPreflightError(tuple(issues))
    return tuple(sorted(chunks, key=lambda item: item.chunk_id))


def write_chunk_artifact(output_path: Path, chunks: tuple[Chunk, ...]) -> bool:
    """Write a fully validated chunk batch."""
    return write_chunks(output_path, chunks)


def _stable_path(path: Path, database: str, filename: str) -> str:
    if not path.is_absolute():
        return path.as_posix()
    try:
        return path.relative_to(Path.cwd()).as_posix()
    except ValueError:
        if filename == "schema.json":
            return f"schema/raw/{database}/schema.json"
        return f"metadata/review/{database}/{filename}"
