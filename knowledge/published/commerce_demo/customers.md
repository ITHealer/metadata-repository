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
source_schema_path: schema/raw/commerce_demo/schema.json
source_review_path: metadata/review/commerce_demo/customers.yml
source_review_commit: a21b31ecc02bc01fd55f0693996b8d6641ef64c0
generator_mode: mock
generator_model: deterministic-v1
prompt_version: deterministic-v1
---

# commerce_demo.customers — Customers

> [!WARNING]
> Preview only: reviewer metadata still has `needs_review` status and must not be indexed.

## Summary

One technical row per customer represented in the ClickHouse demo dataset. Grain: One row per customer_id.

## Grain and purpose

**Grain:** One row per customer_id.
- Support customer-level analysis in the demo dataset.

## Appropriate use

- Join orders to a customer by customer_id.

## Inappropriate use

- Treat synthetic names or emails as real customer contact data.

## Columns

### `created_at` — Customer created time

UTC timestamp recorded when the customer profile was created.

- Technical type: `DateTime`
- Nullable: `false`
- Semantic type: `timestamp`
- Unit/timezone: `UTC`
- Null meaning: not_applicable
- Sensitivity: `internal`

### `customer_id` — Customer identifier

Stable technical identifier for one demo customer.

- Technical type: `UUID`
- Nullable: `false`
- Semantic type: `identifier`
- Unit/timezone: `not_applicable`
- Null meaning: not_applicable
- Sensitivity: `internal`

### `email` — Customer email

Synthetic contact email using the .test domain in this demo.

- Technical type: `String`
- Nullable: `false`
- Semantic type: `email`
- Unit/timezone: `not_applicable`
- Null meaning: not_applicable
- Sensitivity: `pii_synthetic`
- Caveats:
  - Demo-only synthetic value; do not use for contacting a person.

### `full_name` — Customer display name

Synthetic display name used by this demo.

- Technical type: `String`
- Nullable: `false`
- Semantic type: `person_name`
- Unit/timezone: `not_applicable`
- Null meaning: not_applicable
- Sensitivity: `pii_synthetic`
- Caveats:
  - Demo-only synthetic value.

### `segment` — Customer segment

Business segment currently recorded for the customer.

- Technical type: `LowCardinality(String)`
- Nullable: `false`
- Semantic type: `categorical`
- Unit/timezone: `not_applicable`
- Null meaning: not_applicable
- Sensitivity: `internal`
- Allowed values:
  - `enterprise`: Enterprise segment.
  - `premium`: Premium segment.
  - `retail`: Retail segment.
- Caveats:
  - Segment assignment rules require reviewer confirmation.

## Relationships and join risks

Not applicable — no reviewed relationship was supplied.

## Business rules

Not applicable — no reviewed business rule was supplied.

## Time and unit semantics

- `created_at`: semantic type `timestamp`, unit/timezone `UTC`; UTC timestamp recorded when the customer profile was created.
- `segment`: semantic type `categorical`, unit/timezone `not_applicable`; Business segment currently recorded for the customer.

## Data quality and caveats

- Confirm customer_id uniqueness before relying on one-row-per-customer grain.
- Business ownership and refresh expectations require reviewer confirmation.

## Security

- Treat email and full_name as sensitive-looking data even though this fixture is synthetic.

## Evidence

- `proposed` `clickhouse_comment` — `schema/raw/commerce_demo/schema.json#tables.customers.columns.created_at`: Derived from the ClickHouse column comment.
- `proposed` `clickhouse_comment` — `schema/raw/commerce_demo/schema.json#tables.customers.columns.customer_id`: Derived from the ClickHouse column comment.
- `proposed` `clickhouse_comment` — `schema/raw/commerce_demo/schema.json#tables.customers.columns.email`: Derived from the ClickHouse column comment.
- `proposed` `clickhouse_comment` — `schema/raw/commerce_demo/schema.json#tables.customers.columns.full_name`: Derived from the ClickHouse column comment.
- `proposed` `clickhouse_comment` — `schema/raw/commerce_demo/schema.json#tables.customers.columns.segment`: Values are listed in the ClickHouse column comment.
- `proposed` `clickhouse_comment` — `schema/raw/commerce_demo/schema.json#tables.customers.comment`: Technical ClickHouse comment; business meaning still requires reviewer confirmation.
