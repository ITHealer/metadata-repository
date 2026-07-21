---
document_id: commerce_demo.order_items
database: commerce_demo
table: order_items
qualified_name: commerce_demo.order_items
owner: unassigned
reviewer: unassigned
document_status: needs_review
index_eligible: false
schema_hash: 45e278ec62c4da241bb18fa3f89bfdae58ee4e7eb1f37ea7c41a24d0fef1b1db
contract_version: reviewer-v1
review_guideline_version: reviewer-v1
transformation_guideline_version: retrieval-v1
source_schema_path: catalog/commerce_demo/generated/raw/schema.json
source_review_path: catalog/commerce_demo/review/order_items.yml
source_review_commit: 18a7bafb9856ef0cc01180933c697b9ea85ee0df
generator_mode: live
generator_model: gpt-oss-120b
prompt_version: approved-narrative-v1
---

# commerce_demo.order_items — Order items

> [!WARNING]
> Preview only: reviewer metadata still has `needs_review` status and must not be indexed.

## Summary

The `order_items` table in the `commerce_demo` ClickHouse dataset provides one technical row per order line, with the grain defined as one row per `order_id` and `line_number`. Each row includes the line position (`line_number` UInt16, ordinal), a logical foreign key to the parent order (`order_id` UUID), a synthetic product code (`product_code` String), the ordered quantity (`quantity` UInt16, product units) and the unit price (`unit_price` Decimal(18,2) in VND). A technical line amount can be derived as `quantity × unit_price`, though this calculation requires reviewer confirmation. The table is intended for joining order lines to orders and for product‑quantity and order‑line value analysis. Reviewers must confirm uniqueness of the (`order_id`, `line_number`) combination, ownership and refresh expectations, and the treatment of product master semantics, returns, cancellations, taxes and discounts. Freshness is currently unknown. All columns are marked internal sensitivity.

## Grain and purpose

**Grain:** One row per order_id and line_number.
- Support product quantity and order-line value analysis in the demo dataset.

## Appropriate use

- Join order lines to orders by order_id.
- Calculate a technical line amount as quantity multiplied by unit_price.

## Inappropriate use

- Assume product_code is a complete product master record.

## Columns

### `line_number` — Order line number

One-based position of the line within an order.

- Technical type: `UInt16`
- Nullable: `false`
- Semantic type: `ordinal`
- Unit/timezone: `not_applicable`
- Null meaning: not_applicable
- Sensitivity: `internal`

### `order_id` — Order identifier

Identifier used for the logical join to orders.order_id.

- Technical type: `UUID`
- Nullable: `false`
- Semantic type: `foreign_identifier`
- Unit/timezone: `not_applicable`
- Null meaning: not_applicable
- Sensitivity: `internal`
- Caveats:
  - The ClickHouse relation is logical and is not treated as an enforced foreign key.

### `product_code` — Product code

Synthetic product code captured when the order was placed.

- Technical type: `String`
- Nullable: `false`
- Semantic type: `identifier`
- Unit/timezone: `not_applicable`
- Null meaning: not_applicable
- Sensitivity: `internal`
- Caveats:
  - Product master semantics require reviewer confirmation.

### `quantity` — Ordered quantity

Number of product units recorded on the order line.

- Technical type: `UInt16`
- Nullable: `false`
- Semantic type: `count`
- Unit/timezone: `product_unit`
- Null meaning: not_applicable
- Sensitivity: `internal`
- Caveats:
  - Return and cancellation handling require reviewer confirmation.

### `unit_price` — Unit price

Price per product unit captured when the order was placed.

- Technical type: `Decimal(18, 2)`
- Nullable: `false`
- Semantic type: `monetary_amount`
- Unit/timezone: `VND`
- Null meaning: not_applicable
- Sensitivity: `internal`
- Caveats:
  - Tax and discount treatment require reviewer confirmation.

## Relationships and join risks

### order_items_to_orders

Associates each order line with its parent order identifier.

- From: `order_items` columns `order_id`
- To: `orders` columns `order_id`
- Join condition: `order_items.order_id = orders.order_id`
- Cardinality: `many_to_one`
- Optional: `false`
- Row-count risk: `unknown`
- ClickHouse-enforced: `false`
- tbls relation: `order_items.order_id -> orders.order_id`

## Business rules

### Technical line amount

Calculate line amount as quantity multiplied by unit_price when this definition fits the use case.

## Time and unit semantics

- `quantity`: semantic type `count`, unit/timezone `product_unit`; Number of product units recorded on the order line.
- `unit_price`: semantic type `monetary_amount`, unit/timezone `VND`; Price per product unit captured when the order was placed.

## Data quality and caveats

- Confirm that order_id plus line_number is unique before relying on the documented grain.
- Business ownership and refresh expectations require reviewer confirmation.

## Security

Not applicable — no table-level security instruction was supplied.

## Evidence

- `proposed` `clickhouse_comment` — `catalog/commerce_demo/generated/raw/schema.json#tables.order_items.columns`: Formula is inferred from technical column names and requires reviewer confirmation.
- `proposed` `clickhouse_comment` — `catalog/commerce_demo/generated/raw/schema.json#tables.order_items.columns.line_number`: Derived from the ClickHouse column comment.
- `proposed` `clickhouse_comment` — `catalog/commerce_demo/generated/raw/schema.json#tables.order_items.columns.order_id`: Derived from the ClickHouse column comment.
- `proposed` `clickhouse_comment` — `catalog/commerce_demo/generated/raw/schema.json#tables.order_items.columns.product_code`: Derived from the ClickHouse column comment.
- `proposed` `clickhouse_comment` — `catalog/commerce_demo/generated/raw/schema.json#tables.order_items.columns.quantity`: Derived from the ClickHouse column comment.
- `proposed` `clickhouse_comment` — `catalog/commerce_demo/generated/raw/schema.json#tables.order_items.columns.unit_price`: Derived from the ClickHouse column comment.
- `proposed` `clickhouse_comment` — `catalog/commerce_demo/generated/raw/schema.json#tables.order_items.comment`: Technical ClickHouse comment; business meaning still requires reviewer confirmation.
- `proposed` `tbls_relation` — `catalog/commerce_demo/generated/raw/schema.json#relations.order_items_to_orders`: Logical relation configured for tbls; cardinality requires data validation.
