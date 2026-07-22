---
document_id: commerce_demo.orders
database: commerce_demo
table: orders
qualified_name: commerce_demo.orders
owner: unassigned
reviewer: unassigned
document_status: needs_review
index_eligible: false
schema_hash: 1f74d093a952f602fee4fbafe6f03770d5849ee090886dc5b765e9d28fda58e5
contract_version: reviewer-v1
review_guideline_version: reviewer-v1
transformation_guideline_version: retrieval-v1
source_schema_path: catalog/commerce_demo/generated/raw/schema.json
source_review_path: catalog/commerce_demo/review/orders.yml
source_review_commit: 271ebb20148f5bb4ee9d9e4b552b792e2adb2b5e
generator_mode: live
generator_model: gpt-oss-120b
prompt_version: workflow-neutral-narrative-v2
---

# commerce_demo.orders — Orders

> [!WARNING]
> Preview only: reviewer metadata still has `needs_review` status and must not be indexed.

## Summary

The Orders table stores a single row per order_id, with columns order_id (stable UUID), customer_id (UUID), created_at and updated_at (UTC timestamps), channel (web, mobile, or partner), order_status (pending, paid, shipped, or cancelled), and total_amount (VND). Cancelled orders remain in the table. Grain and detailed business interpretation are pending confirmation.

## Grain and purpose

**Grain:** Unknown — needs confirmation
- Unknown — needs confirmation

## Appropriate use

- Unknown — needs confirmation

## Inappropriate use

- Unknown — needs confirmation

## Columns

### `channel` — Channel

Order acquisition channel: web, mobile, or partner

- Technical type: `LowCardinality(String)`
- Nullable: `false`
- Semantic type: `unknown`
- Unit/timezone: `not_applicable`
- Null meaning: not_applicable
- Sensitivity: `internal`

### `created_at` — Created At

UTC timestamp when the order was created

- Technical type: `DateTime`
- Nullable: `false`
- Semantic type: `timestamp`
- Unit/timezone: `UTC`
- Null meaning: not_applicable
- Sensitivity: `internal`

### `customer_id` — Customer Id

Customer that placed the order; logical join to customers.customer_id

- Technical type: `UUID`
- Nullable: `false`
- Semantic type: `identifier`
- Unit/timezone: `not_applicable`
- Null meaning: not_applicable
- Sensitivity: `internal`

### `order_id` — Order Id

Stable identifier for one order

- Technical type: `UUID`
- Nullable: `false`
- Semantic type: `identifier`
- Unit/timezone: `not_applicable`
- Null meaning: not_applicable
- Sensitivity: `internal`

### `order_status` — Order Status

Current lifecycle state: pending, paid, shipped, or cancelled

- Technical type: `LowCardinality(String)`
- Nullable: `false`
- Semantic type: `categorical`
- Unit/timezone: `not_applicable`
- Null meaning: not_applicable
- Sensitivity: `internal`
- Caveats:
  - Allowed values require reviewer confirmation.

### `total_amount` — Total Amount

Order total in VND after discounts

- Technical type: `Decimal(18, 2)`
- Nullable: `false`
- Semantic type: `monetary_amount`
- Unit/timezone: `VND`
- Null meaning: not_applicable
- Sensitivity: `internal`

### `updated_at` — Updated At

UTC timestamp of the latest order update

- Technical type: `DateTime`
- Nullable: `false`
- Semantic type: `timestamp`
- Unit/timezone: `UTC`
- Null meaning: not_applicable
- Sensitivity: `internal`

## Relationships and join risks

Not applicable — no reviewed relationship was supplied.

## Business rules

Not applicable — no reviewed business rule was supplied.

## Time and unit semantics

- `created_at`: semantic type `timestamp`, unit/timezone `UTC`; UTC timestamp when the order was created
- `order_status`: semantic type `categorical`, unit/timezone `not_applicable`; Current lifecycle state: pending, paid, shipped, or cancelled
- `total_amount`: semantic type `monetary_amount`, unit/timezone `VND`; Order total in VND after discounts
- `updated_at`: semantic type `timestamp`, unit/timezone `UTC`; UTC timestamp of the latest order update

## Data quality and caveats

- Data quality expectations require reviewer confirmation.
- Business meaning requires domain reviewer confirmation.

## Security

Not applicable — no table-level security instruction was supplied.

## Evidence

- `proposed` `clickhouse_comment` — `build/schema-sync/staging/live-create-additive/commerce_demo/raw/schema.json#tables.orders.columns.channel`: Generated from the ClickHouse comment; domain confirmation is required.
- `proposed` `clickhouse_comment` — `catalog/commerce_demo/generated/raw/schema.json#tables.orders.columns.created_at`: Generated from the ClickHouse comment; domain confirmation is required.
- `proposed` `clickhouse_comment` — `catalog/commerce_demo/generated/raw/schema.json#tables.orders.columns.customer_id`: Generated from the ClickHouse comment; domain confirmation is required.
- `proposed` `clickhouse_comment` — `catalog/commerce_demo/generated/raw/schema.json#tables.orders.columns.order_id`: Generated from the ClickHouse comment; domain confirmation is required.
- `proposed` `clickhouse_comment` — `catalog/commerce_demo/generated/raw/schema.json#tables.orders.columns.order_status`: Generated from the ClickHouse comment; domain confirmation is required.
- `proposed` `clickhouse_comment` — `catalog/commerce_demo/generated/raw/schema.json#tables.orders.columns.total_amount`: Generated from the ClickHouse comment; domain confirmation is required.
- `proposed` `clickhouse_comment` — `catalog/commerce_demo/generated/raw/schema.json#tables.orders.columns.updated_at`: Generated from the ClickHouse comment; domain confirmation is required.
- `proposed` `clickhouse_comment` — `catalog/commerce_demo/generated/raw/schema.json#tables.orders.comment`: Generated from the ClickHouse comment; domain confirmation is required.
