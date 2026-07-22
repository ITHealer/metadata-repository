---
document_id: commerce_demo.customers
database: commerce_demo
table: customers
qualified_name: commerce_demo.customers
owner: unassigned
reviewer: unassigned
document_status: needs_review
index_eligible: false
schema_hash: b6d19bdd84422c798d5c173b01e4e52337d37c830346cad16a4e79319a8c07dc
contract_version: reviewer-v1
review_guideline_version: reviewer-v1
transformation_guideline_version: retrieval-v1
source_schema_path: catalog/commerce_demo/generated/raw/schema.json
source_review_path: catalog/commerce_demo/review/customers.yml
source_review_commit: b3cd2b5f5b941e655a403335a8d1ace77a8c77d2
generator_mode: live
generator_model: gpt-oss-120b
prompt_version: workflow-neutral-narrative-v2
---

# commerce_demo.customers — Customers

> [!WARNING]
> Preview only: reviewer metadata still has `needs_review` status and must not be indexed.

## Summary

The customers table is a dimension with one row per customer, containing a stable UUID, UTC creation timestamp, synthetic email (PII‑like) and full name, and a segment field (retail, premium, or enterprise). All values are synthetic; the grain, freshness, appropriate use, and many business meanings remain unconfirmed and require domain reviewer verification.

## Grain and purpose

**Grain:** Unknown — needs confirmation
- Unknown — needs confirmation

## Appropriate use

- Unknown — needs confirmation

## Inappropriate use

- Unknown — needs confirmation

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
- Sensitivity: `unknown`

### `full_name` — Full Name

Display name; synthetic data used only by this demo

- Technical type: `String`
- Nullable: `false`
- Semantic type: `person_name`
- Unit/timezone: `not_applicable`
- Null meaning: not_applicable
- Sensitivity: `unknown`

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
- Business meaning requires domain reviewer confirmation.

## Security

Not applicable — no table-level security instruction was supplied.

## Evidence

- `proposed` `clickhouse_comment` — `catalog/commerce_demo/generated/raw/schema.json#tables.customers.columns.created_at`: Generated from the ClickHouse comment; domain confirmation is required.
- `proposed` `clickhouse_comment` — `catalog/commerce_demo/generated/raw/schema.json#tables.customers.columns.customer_id`: Generated from the ClickHouse comment; domain confirmation is required.
- `proposed` `clickhouse_comment` — `catalog/commerce_demo/generated/raw/schema.json#tables.customers.columns.email`: Generated from the ClickHouse comment; domain confirmation is required.
- `proposed` `clickhouse_comment` — `catalog/commerce_demo/generated/raw/schema.json#tables.customers.columns.full_name`: Generated from the ClickHouse comment; domain confirmation is required.
- `proposed` `clickhouse_comment` — `catalog/commerce_demo/generated/raw/schema.json#tables.customers.columns.segment`: Generated from the ClickHouse comment; domain confirmation is required.
- `proposed` `clickhouse_comment` — `catalog/commerce_demo/generated/raw/schema.json#tables.customers.comment`: Generated from the ClickHouse comment; domain confirmation is required.
