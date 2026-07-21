---
document_id: commerce_demo.order_items
database: commerce_demo
table: order_items
qualified_name: commerce_demo.order_items
owner: unassigned
reviewer: unassigned
document_status: approved
index_eligible: true
schema_hash: 45e278ec62c4da241bb18fa3f89bfdae58ee4e7eb1f37ea7c41a24d0fef1b1db
contract_version: reviewer-v1
review_guideline_version: reviewer-v1
transformation_guideline_version: retrieval-v1
source_schema_path: catalog/commerce_demo/generated/raw/schema.json
source_review_path: catalog/commerce_demo/review/order_items.yml
source_review_commit: bf1a1253b23629c6053e1cd42797bbbc6dcccd00
generator_mode: live
generator_model: gpt-oss-120b
prompt_version: workflow-neutral-narrative-v2
---

# commerce_demo.order_items — Order Items

## Summary

The Order Items table (commerce_demo.order_items) records a fact per order line, with one row per order_id and line_number (grain currently unconfirmed). Each row includes the line_number (one‑based position in the order), the order_id (identifier linking to the parent order), the product_code captured at purchase, the quantity of units (count, unit unknown), and the unit_price in VND (monetary amount). The table stores internal‑sensitivity data and its freshness, purpose, and appropriate use are still pending domain confirmation.

## Grain and purpose

**Grain:** Unknown — needs confirmation
- Unknown — needs confirmation

## Appropriate use

- Unknown — needs confirmation

## Inappropriate use

- Unknown — needs confirmation

## Columns

### `line_number` — Line Number

One-based line position within an order

- Technical type: `UInt16`
- Nullable: `false`
- Semantic type: `unknown`
- Unit/timezone: `not_applicable`
- Null meaning: not_applicable
- Sensitivity: `internal`

### `order_id` — Order Id

Parent order; logical join to orders.order_id

- Technical type: `UUID`
- Nullable: `false`
- Semantic type: `identifier`
- Unit/timezone: `not_applicable`
- Null meaning: not_applicable
- Sensitivity: `internal`

### `product_code` — Product Code

Synthetic product code captured when the order was placed

- Technical type: `String`
- Nullable: `false`
- Semantic type: `identifier`
- Unit/timezone: `not_applicable`
- Null meaning: not_applicable
- Sensitivity: `internal`

### `quantity` — Quantity

Number of product units on this order line

- Technical type: `UInt16`
- Nullable: `false`
- Semantic type: `count`
- Unit/timezone: `Unknown — needs confirmation`
- Null meaning: not_applicable
- Sensitivity: `internal`

### `unit_price` — Unit Price

Price per unit in VND when the order was placed

- Technical type: `Decimal(18, 2)`
- Nullable: `false`
- Semantic type: `monetary_amount`
- Unit/timezone: `VND`
- Null meaning: not_applicable
- Sensitivity: `internal`

## Relationships and join risks

Not applicable — no reviewed relationship was supplied.

## Business rules

Not applicable — no reviewed business rule was supplied.

## Time and unit semantics

- `quantity`: semantic type `count`, unit/timezone `Unknown — needs confirmation`; Number of product units on this order line
- `unit_price`: semantic type `monetary_amount`, unit/timezone `VND`; Price per unit in VND when the order was placed

## Data quality and caveats

- Data quality expectations require reviewer confirmation.
- Business meaning requires domain reviewer confirmation.

## Security

Not applicable — no table-level security instruction was supplied.

## Evidence

- `proposed` `clickhouse_comment` — `catalog/commerce_demo/generated/raw/schema.json#tables.order_items.columns.line_number`: Generated from the ClickHouse comment; domain confirmation is required.
- `proposed` `clickhouse_comment` — `catalog/commerce_demo/generated/raw/schema.json#tables.order_items.columns.order_id`: Generated from the ClickHouse comment; domain confirmation is required.
- `proposed` `clickhouse_comment` — `catalog/commerce_demo/generated/raw/schema.json#tables.order_items.columns.product_code`: Generated from the ClickHouse comment; domain confirmation is required.
- `proposed` `clickhouse_comment` — `catalog/commerce_demo/generated/raw/schema.json#tables.order_items.columns.quantity`: Generated from the ClickHouse comment; domain confirmation is required.
- `proposed` `clickhouse_comment` — `catalog/commerce_demo/generated/raw/schema.json#tables.order_items.columns.unit_price`: Generated from the ClickHouse comment; domain confirmation is required.
- `proposed` `clickhouse_comment` — `catalog/commerce_demo/generated/raw/schema.json#tables.order_items.comment`: Generated from the ClickHouse comment; domain confirmation is required.
