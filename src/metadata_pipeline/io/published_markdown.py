"""Deterministic Markdown rendering for structured published metadata."""

from __future__ import annotations

from pathlib import Path

import yaml

from metadata_pipeline.domain.published import PublishedDocument
from metadata_pipeline.domain.review import DocumentStatus, Evidence
from metadata_pipeline.io.atomic_text import write_text_if_changed


def render_published_document(document: PublishedDocument) -> str:
    """Render stable front matter and non-empty retrieval-oriented sections."""
    front_matter = {
        "document_id": document.document_id,
        "database": document.database,
        "table": document.table,
        "qualified_name": document.qualified_name,
        "owner": document.owner,
        "reviewer": document.reviewer,
        "document_status": document.document_status.value,
        "index_eligible": document.index_eligible,
        "schema_hash": document.schema_hash,
        "contract_version": document.contract_version,
        "review_guideline_version": document.review_guideline_version,
        "transformation_guideline_version": document.transformation_guideline_version,
        "source_schema_path": document.provenance.source_schema_path,
        "source_review_path": document.provenance.source_review_path,
        "source_review_commit": document.provenance.source_review_commit,
        "generator_mode": document.provenance.generator_mode.value,
        "generator_model": document.provenance.generator_model,
        "prompt_version": document.provenance.prompt_version,
    }
    parts = [
        "---",
        yaml.safe_dump(front_matter, allow_unicode=True, sort_keys=False).rstrip(),
        "---",
        "",
        f"# {document.qualified_name} — {document.display_name}",
        "",
    ]
    if document.document_status is DocumentStatus.NEEDS_REVIEW:
        parts.extend(
            [
                "> [!WARNING]",
                "> Preview only: reviewer metadata still has `needs_review` status "
                "and must not be indexed.",
                "",
            ]
        )
    _section(parts, "Summary", (document.summary,))
    _section(
        parts,
        "Grain and purpose",
        (f"**Grain:** {document.grain}", *_bullets(document.purpose)),
    )
    _section(parts, "Appropriate use", _bullets(document.appropriate_use))
    _section(parts, "Inappropriate use", _bullets(document.inappropriate_use))
    _render_columns(parts, document)
    _render_relationships(parts, document)
    _render_rules(parts, document)
    _render_time_and_units(parts, document)
    _section(
        parts,
        "Data quality and caveats",
        _bullets((*document.data_quality, *document.caveats)),
        "Not applicable — no data-quality issue or table caveat was supplied.",
    )
    _section(
        parts,
        "Security",
        _bullets(document.security),
        "Not applicable — no table-level security instruction was supplied.",
    )
    _render_evidence(parts, document)
    return "\n".join(parts).rstrip() + "\n"


def write_published_document(path: Path, document: PublishedDocument) -> bool:
    """Atomically write one changed published document."""
    return write_text_if_changed(path, render_published_document(document))


def _section(
    parts: list[str],
    heading: str,
    lines: tuple[str, ...],
    empty_message: str = "Not applicable — no reviewer metadata was supplied.",
) -> None:
    parts.extend((f"## {heading}", ""))
    parts.extend(lines or (empty_message,))
    parts.append("")


def _bullets(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(f"- {value}" for value in values)


def _render_columns(parts: list[str], document: PublishedDocument) -> None:
    parts.extend(("## Columns", ""))
    for column in document.columns:
        parts.extend(
            (
                f"### `{column.name}` — {column.business_name}",
                "",
                column.description,
                "",
                f"- Technical type: `{column.data_type}`",
                f"- Nullable: `{str(column.nullable).lower()}`",
                f"- Semantic type: `{column.semantic_type}`",
                f"- Unit/timezone: `{column.unit}`",
                f"- Null meaning: {column.nullable_meaning}",
                f"- Sensitivity: `{column.sensitivity}`",
            )
        )
        if column.allowed_values:
            parts.append("- Allowed values:")
            parts.extend(
                f"  - `{value}`: {meaning}"
                for value, meaning in sorted(column.allowed_values.items())
            )
        if column.caveats:
            parts.append("- Caveats:")
            parts.extend(f"  - {caveat}" for caveat in column.caveats)
        parts.append("")


def _render_relationships(parts: list[str], document: PublishedDocument) -> None:
    parts.extend(("## Relationships and join risks", ""))
    if not document.relationships:
        parts.extend(("Not applicable — no reviewed relationship was supplied.", ""))
        return
    for relationship in document.relationships:
        parts.extend(
            (
                f"### {relationship.name}",
                "",
                relationship.meaning,
                "",
                f"- From: `{relationship.from_table}` columns "
                f"{_code_list(relationship.from_columns)}",
                f"- To: `{relationship.to_table}` columns {_code_list(relationship.to_columns)}",
                f"- Join condition: `{relationship.join_condition}`",
                f"- Cardinality: `{relationship.cardinality.value}`",
                f"- Optional: `{str(relationship.optional).lower()}`",
                f"- Row-count risk: `{relationship.row_count_impact.value}`",
                "- ClickHouse-enforced: `false`",
            )
        )
        if relationship.technical_definition:
            parts.append(f"- tbls relation: `{relationship.technical_definition}`")
        parts.append("")


def _render_rules(parts: list[str], document: PublishedDocument) -> None:
    parts.extend(("## Business rules", ""))
    if not document.business_rules:
        parts.extend(("Not applicable — no reviewed business rule was supplied.", ""))
        return
    for rule in document.business_rules:
        parts.extend((f"### {rule.name}", "", rule.description, ""))


def _render_time_and_units(parts: list[str], document: PublishedDocument) -> None:
    semantic_columns = tuple(
        column
        for column in document.columns
        if column.semantic_type.lower()
        in {
            "timestamp",
            "date",
            "monetary_amount",
            "measure",
            "count",
            "percentage",
            "duration",
            "categorical",
            "status",
            "code",
        }
    )
    lines = tuple(
        f"- `{column.name}`: semantic type `{column.semantic_type}`, unit/timezone "
        f"`{column.unit}`; {column.description}"
        for column in semantic_columns
    )
    _section(
        parts,
        "Time and unit semantics",
        lines,
        "Not applicable — no timestamp, measure, status, or code column was supplied.",
    )


def _render_evidence(parts: list[str], document: PublishedDocument) -> None:
    evidence = _all_evidence(document)
    lines = tuple(
        f"- `{item.status.value}` `{item.kind.value}` — `{item.reference}`"
        + (f": {item.note}" if item.note else "")
        for item in evidence
    )
    _section(parts, "Evidence", lines)


def _all_evidence(document: PublishedDocument) -> tuple[Evidence, ...]:
    values = list(document.business_evidence)
    for column in document.columns:
        values.extend(column.evidence)
    for relationship in document.relationships:
        values.extend(relationship.evidence)
    for rule in document.business_rules:
        values.extend(rule.evidence)
    unique = {
        (item.kind.value, item.reference, item.status.value, item.note): item for item in values
    }
    return tuple(unique[key] for key in sorted(unique))


def _code_list(values: tuple[str, ...]) -> str:
    return ", ".join(f"`{value}`" for value in values)
