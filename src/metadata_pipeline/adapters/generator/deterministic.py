"""Network-free published document generator used as the factual baseline."""

from __future__ import annotations

from dataclasses import dataclass

from metadata_pipeline.domain.hashing import table_schema_hash
from metadata_pipeline.domain.published import (
    GeneratorMode,
    Provenance,
    PublishedColumn,
    PublishedDocument,
    PublishedRelationship,
    PublishedRule,
)
from metadata_pipeline.domain.review import DocumentStatus, RelationshipReview
from metadata_pipeline.ports.document_generator import (
    DocumentGenerationError,
    PublicationContext,
)
from metadata_pipeline.ports.schema_source import RelationSchema


@dataclass(frozen=True)
class DeterministicDocumentGenerator:
    """Merge raw and reviewer facts without adding model-generated claims."""

    model_name: str = "deterministic-v1"

    def generate(self, context: PublicationContext) -> PublishedDocument:
        """Return a stable document whose technical values come only from raw schema."""
        _validate_context(context)
        review = context.review
        business = review.business
        qualified_name = f"{review.database}.{review.table}"
        relations = tuple(
            _published_relationship(context, relationship) for relationship in review.relationships
        )
        columns = tuple(
            PublishedColumn(
                name=column.name,
                data_type=column.data_type,
                nullable=column.nullable,
                technical_comment=column.comment,
                business_name=review.columns[column.name].business_name,
                description=review.columns[column.name].description,
                semantic_type=review.columns[column.name].semantic_type,
                unit=review.columns[column.name].unit,
                nullable_meaning=review.columns[column.name].nullable_meaning,
                sensitivity=review.columns[column.name].sensitivity,
                allowed_values=review.columns[column.name].allowed_values,
                caveats=review.columns[column.name].caveats,
                evidence=review.columns[column.name].evidence,
            )
            for column in sorted(context.table.columns, key=lambda item: item.name)
        )
        return PublishedDocument(
            document_id=qualified_name,
            database=review.database,
            table=review.table,
            qualified_name=qualified_name,
            owner=review.owner,
            reviewer=review.reviewer,
            document_status=review.document_status,
            index_eligible=review.document_status is DocumentStatus.APPROVED,
            schema_hash=review.schema_hash,
            contract_version=review.contract_version,
            review_guideline_version=review.review_guideline_version,
            transformation_guideline_version=review.transformation_guideline_version,
            provenance=Provenance(
                source_schema_path=context.source_schema_path,
                source_review_path=context.source_review_path,
                source_review_commit=context.source_review_commit,
                generator_mode=GeneratorMode.MOCK,
                generator_model=self.model_name,
            ),
            display_name=business.display_name,
            summary=f"{business.description} Grain: {business.grain}",
            description=business.description,
            grain=business.grain,
            purpose=business.purpose,
            appropriate_use=business.appropriate_use,
            inappropriate_use=business.inappropriate_use,
            aliases=business.aliases,
            freshness=business.freshness,
            caveats=business.caveats,
            business_evidence=business.evidence,
            columns=columns,
            relationships=relations,
            business_rules=tuple(
                PublishedRule(
                    name=rule.name,
                    description=rule.description,
                    evidence=rule.evidence,
                )
                for rule in review.business_rules
            ),
            data_quality=review.data_quality,
            security=review.security,
        )


def _validate_context(context: PublicationContext) -> None:
    review = context.review
    if context.schema.name != review.database:
        raise DocumentGenerationError("review database does not match raw schema")
    if context.table.name != review.table:
        raise DocumentGenerationError("review table does not match raw table")
    expected_hash = table_schema_hash(context.schema, context.table)
    if review.schema_hash != expected_hash:
        raise DocumentGenerationError("review schema_hash is stale")
    raw_columns = {column.name for column in context.table.columns}
    if raw_columns != set(review.columns):
        raise DocumentGenerationError("review columns do not exactly match raw table columns")


def _published_relationship(
    context: PublicationContext,
    relationship: RelationshipReview,
) -> PublishedRelationship:
    technical = _find_technical_relation(context, relationship)
    return PublishedRelationship(
        name=relationship.name,
        from_table=context.table.name,
        from_columns=relationship.from_columns,
        to_table=relationship.to_table,
        to_columns=relationship.to_columns,
        join_condition=relationship.join_condition,
        cardinality=relationship.cardinality,
        optional=relationship.optional,
        row_count_impact=relationship.row_count_impact,
        meaning=relationship.meaning,
        technical_definition=technical.definition if technical else None,
        virtual=technical.virtual if technical else None,
        evidence=relationship.evidence,
    )


def _find_technical_relation(
    context: PublicationContext,
    relationship: RelationshipReview,
) -> RelationSchema | None:
    for relation in context.schema.relations:
        if (
            relation.table == context.table.name
            and relation.columns == relationship.from_columns
            and relation.parent_table == relationship.to_table
            and relation.parent_columns == relationship.to_columns
        ):
            return relation
    return None
