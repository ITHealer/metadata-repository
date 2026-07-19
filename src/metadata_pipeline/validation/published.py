"""Validation that published structured output still matches its source contracts."""

from __future__ import annotations

from pathlib import Path

from metadata_pipeline.adapters.generator.deterministic import DeterministicDocumentGenerator
from metadata_pipeline.domain.published import PublishedDocument
from metadata_pipeline.ports.document_generator import DocumentGenerationError, PublicationContext
from metadata_pipeline.validation.review import ValidationIssue


def validate_published_document(
    context: PublicationContext,
    document: PublishedDocument,
    path: Path,
) -> tuple[ValidationIssue, ...]:
    """Require all non-narrative output fields to match the deterministic baseline."""
    try:
        baseline = DeterministicDocumentGenerator().generate(context)
    except DocumentGenerationError as error:
        return (ValidationIssue("invalid_publication_context", path, "$", str(error)),)

    expected_provenance = baseline.provenance.model_copy(
        update={
            "generator_mode": document.provenance.generator_mode,
            "generator_model": document.provenance.generator_model,
        }
    )
    expected = baseline.model_copy(
        update={
            "summary": document.summary,
            "provenance": expected_provenance,
        }
    )
    expected_payload = expected.model_dump(mode="json")
    actual_payload = document.model_dump(mode="json")
    issues: list[ValidationIssue] = []
    _compare_values(issues, path, "$", expected_payload, actual_payload)
    return tuple(issues)


def _compare_values(
    issues: list[ValidationIssue],
    path: Path,
    field: str,
    expected: object,
    actual: object,
) -> None:
    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in sorted(set(expected) | set(actual)):
            child = f"{field}.{key}"
            if key not in expected or key not in actual:
                issues.append(
                    ValidationIssue(
                        "published_source_drift",
                        path,
                        child,
                        "published field set does not match the source contract",
                    )
                )
                continue
            _compare_values(issues, path, child, expected[key], actual[key])
        return
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            issues.append(
                ValidationIssue(
                    "published_source_drift",
                    path,
                    field,
                    f"expected {len(expected)} item(s), found {len(actual)}",
                )
            )
            return
        for index, (expected_item, actual_item) in enumerate(zip(expected, actual)):
            _compare_values(issues, path, f"{field}.{index}", expected_item, actual_item)
        return
    if expected != actual:
        issues.append(
            ValidationIssue(
                "published_source_drift",
                path,
                field,
                f"expected {expected!r}, found {actual!r}",
            )
        )
