---
document_id: commerce_demo.customers
database: commerce_demo
table: customers
qualified_name: commerce_demo.customers
owner: customer-analytics
reviewer: hoai.um
document_status: needs_review
index_eligible: false
schema_hash: b6d19bdd84422c798d5c173b01e4e52337d37c830346cad16a4e79319a8c07dc
contract_version: reviewer-v1
review_guideline_version: reviewer-v1
transformation_guideline_version: retrieval-v1
source_schema_path: catalog/commerce_demo/generated/raw/schema.json
source_review_path: catalog/commerce_demo/review/customers.yml
source_review_commit: 95e2beb1427368168f6825cdf16e47b1801790aa
generator_mode: live
generator_model: gpt-oss-120b
prompt_version: workflow-neutral-narrative-v2
---

# commerce_demo.customers — Customer Dimension

> [!WARNING]
> Preview only: reviewer metadata still has `needs_review` status and must not be indexed.

## Summary

The table provides one synthetic demo customer per row (grain: customer_id) with a creation timestamp, stable UUID, synthetic email and name (PII‑synthetic), and a segment label (retail, premium, or enterprise). It is intended for analyzing order behavior across these business segments, not for production master data or contacting the synthetic contacts.

## Grain and purpose

**Grain:** One row per customer_id.
- Analyze order behavior by customer segment in the commerce demo.

## Appropriate use

- Group order metrics by retail, premium, or enterprise customer segment.

## Inappropriate use

- Do not use this table as a production customer master.
- Do not use synthetic email or full name values to contact customers.

## Columns

### `created_at` — Created At

UTC timestamp when the customer profile was created

- Technical type: `DateTime`
- Nullable: `false`
- Semantic type: `timestamp`
- Unit/timezone: `UTC`
- Null meaning: not_applicable
- Sensitivity: `internal`

### `customer_id` — Customer Id

Stable identifier for one demo customer

- Technical type: `UUID`
- Nullable: `false`
- Semantic type: `identifier`
- Unit/timezone: `not_applicable`
- Null meaning: not_applicable
- Sensitivity: `internal`

### `email` — Email

Synthetic contact email classified as PII; always uses the .test domain

- Technical type: `String`
- Nullable: `false`
- Semantic type: `email`
- Unit/timezone: `not_applicable`
- Null meaning: not_applicable
- Sensitivity: `pii_synthetic`

### `full_name` — Full Name

Display name; synthetic data used only by this demo

- Technical type: `String`
- Nullable: `false`
- Semantic type: `person_name`
- Unit/timezone: `not_applicable`
- Null meaning: not_applicable
- Sensitivity: `pii_synthetic`

### `segment` — Segment

Business segment: retail, premium, or enterprise

- Technical type: `LowCardinality(String)`
- Nullable: `false`
- Semantic type: `categorical`
- Unit/timezone: `not_applicable`
- Null meaning: not_applicable
- Sensitivity: `internal`
- Caveats:
  - Allowed values require reviewer confirmation.

## Relationships and join risks

Not applicable — no reviewed relationship was supplied.

## Business rules

Not applicable — no reviewed business rule was supplied.

## Time and unit semantics

- `created_at`: semantic type `timestamp`, unit/timezone `UTC`; UTC timestamp when the customer profile was created
- `segment`: semantic type `categorical`, unit/timezone `not_applicable`; Business segment: retail, premium, or enterprise

## Data quality and caveats

- Data quality expectations require reviewer confirmation.
- Email and full name are synthetic PII-like test values.

## Security

Not applicable — no table-level security instruction was supplied.

## Evidence

- `proposed` `clickhouse_comment` — `catalog/commerce_demo/generated/raw/schema.json#tables.customers.columns.created_at`: Generated from the ClickHouse comment; domain confirmation is required.
- `proposed` `clickhouse_comment` — `catalog/commerce_demo/generated/raw/schema.json#tables.customers.columns.customer_id`: Generated from the ClickHouse comment; domain confirmation is required.
- `proposed` `clickhouse_comment` — `catalog/commerce_demo/generated/raw/schema.json#tables.customers.columns.email`: Generated from the ClickHouse comment; domain confirmation is required.
- `proposed` `clickhouse_comment` — `catalog/commerce_demo/generated/raw/schema.json#tables.customers.columns.full_name`: Generated from the ClickHouse comment; domain confirmation is required.
- `proposed` `clickhouse_comment` — `catalog/commerce_demo/generated/raw/schema.json#tables.customers.columns.segment`: Generated from the ClickHouse comment; domain confirmation is required.
- `proposed` `clickhouse_comment` — `catalog/commerce_demo/generated/raw/schema.json#tables.customers.comment`: Generated from the ClickHouse comment; domain confirmation is required.
