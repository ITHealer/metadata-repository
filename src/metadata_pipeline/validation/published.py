"""Validation that published structured output still matches its source contracts."""

from __future__ import annotations

from pathlib import Path

from metadata_pipeline.adapters.generator.deterministic import DeterministicDocumentGenerator
from metadata_pipeline.domain.published import GeneratorMode, PublishedDocument
from metadata_pipeline.domain.review import DocumentStatus
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
            "prompt_version": document.provenance.prompt_version,
        }
    )
    allowed_updates: dict[str, object] = {
        "summary": document.summary,
        "provenance": expected_provenance,
    }
    if (
        document.provenance.generator_mode is GeneratorMode.LIVE
        and document.document_status is DocumentStatus.APPROVED
    ):
        actual_columns = {column.name: column for column in document.columns}
        actual_relationships = {
            relationship.name: relationship for relationship in document.relationships
        }
        actual_rules = {rule.name: rule for rule in document.business_rules}
        allowed_updates.update(
            {
                "description": document.description,
                "purpose": document.purpose,
                "appropriate_use": document.appropriate_use,
                "inappropriate_use": document.inappropriate_use,
                "columns": tuple(
                    column.model_copy(
                        update={"description": actual_columns.get(column.name, column).description}
                    )
                    for column in baseline.columns
                ),
                "relationships": tuple(
                    relationship.model_copy(
                        update={
                            "meaning": actual_relationships.get(
                                relationship.name, relationship
                            ).meaning
                        }
                    )
                    for relationship in baseline.relationships
                ),
                "business_rules": tuple(
                    rule.model_copy(
                        update={"description": actual_rules.get(rule.name, rule).description}
                    )
                    for rule in baseline.business_rules
                ),
            }
        )
    expected = baseline.model_copy(update=allowed_updates)
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
