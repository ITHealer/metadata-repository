"""Provider-neutral published document generation boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from metadata_pipeline.domain.published import PublishedDocument
from metadata_pipeline.domain.review import ReviewDocument
from metadata_pipeline.ports.schema_source import DatabaseSchema, TableSchema


class DocumentGenerationError(ValueError):
    """Raised when a generator cannot return a trustworthy document."""


@dataclass(frozen=True)
class PublicationContext:
    """Validated sources supplied to any deterministic or live generator."""

    schema: DatabaseSchema
    table: TableSchema
    review: ReviewDocument
    source_schema_path: str
    source_review_path: str
    source_review_commit: str


class DocumentGenerator(Protocol):
    """Generate the same structured contract regardless of model provider."""

    def generate(self, context: PublicationContext) -> PublishedDocument:
        """Return one validated published document or raise a generation error."""
