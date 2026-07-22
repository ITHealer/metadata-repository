"""Deterministic table-level summary for automated schema synchronization PRs."""

from __future__ import annotations

from dataclasses import dataclass

from metadata_pipeline.ports.schema_source import DatabaseSchema, RelationSchema


@dataclass(frozen=True)
class SchemaSyncSummary:
    """Added, modified, deleted tables and reviewer files requiring attention."""

    added: tuple[str, ...]
    modified: tuple[str, ...]
    deleted: tuple[str, ...]
    review_files: tuple[str, ...]

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.modified or self.deleted)


def summarize_schema_change(
    before: DatabaseSchema,
    after: DatabaseSchema,
    database_key: str | None = None,
) -> SchemaSyncSummary:
    """Compare provider-neutral catalogs without parsing generated Markdown."""
    before_tables = {table.name: table for table in before.tables}
    after_tables = {table.name: table for table in after.tables}
    before_names = set(before_tables)
    after_names = set(after_tables)
    added = tuple(sorted(after_names - before_names))
    deleted = tuple(sorted(before_names - after_names))
    modified_names = {
        name for name in before_names & after_names if before_tables[name] != after_tables[name]
    }
    before_relations = _relations_by_table(before)
    after_relations = _relations_by_table(after)
    for name in before_names & after_names:
        if before_relations.get(name, ()) != after_relations.get(name, ()):
            modified_names.add(name)
    modified = tuple(sorted(modified_names))
    affected = set((*added, *modified, *deleted))
    catalog_database = database_key or after.name
    return SchemaSyncSummary(
        added=added,
        modified=modified,
        deleted=deleted,
        review_files=tuple(
            f"catalog/{catalog_database}/review/{name}.yml" for name in sorted(affected)
        ),
    )


def render_schema_sync_pr_body(summary: SchemaSyncSummary) -> str:
    """Render stable Markdown suitable for a draft Pull Request body."""
    lines = [
        "## Automated ClickHouse schema sync",
        "",
        "This draft was generated from the reproducible ClickHouse/tbls synchronization workflow.",
        "A domain reviewer must complete affected reviewer YAML before approval.",
        "",
        "| Change | Tables |",
        "|---|---|",
        f"| Added | {_display(summary.added)} |",
        f"| Modified | {_display(summary.modified)} |",
        f"| Deleted | {_display(summary.deleted)} |",
        "",
        "## Reviewer attention",
        "",
    ]
    if summary.review_files:
        lines.extend(f"- `{path}`" for path in summary.review_files)
    else:
        lines.append("- No reviewer file requires changes.")
    lines.extend(
        (
            "",
            "Run `make review-validate` after resolving draft fields, then let the Metadata PR bot "
            "regenerate published output.",
            "",
        )
    )
    return "\n".join(lines)


def _relations_by_table(schema: DatabaseSchema) -> dict[str, tuple[RelationSchema, ...]]:
    values: dict[str, list[RelationSchema]] = {}
    for relation in schema.relations:
        values.setdefault(relation.table, []).append(relation)
        values.setdefault(relation.parent_table, []).append(relation)
    return {name: tuple(sorted(relations, key=repr)) for name, relations in values.items()}


def _display(values: tuple[str, ...]) -> str:
    return ", ".join(f"`{value}`" for value in values) if values else "None"
