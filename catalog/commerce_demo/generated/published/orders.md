---
document_id: commerce_demo.orders
database: commerce_demo
table: orders
qualified_name: commerce_demo.orders
owner: commerce-team
reviewer: ITHealer
document_status: approved
index_eligible: true
schema_hash: 35f5ee5a72b251a7e6269c5714f98dab9952db4f0dcf14c98cc11250c6f81f06
contract_version: reviewer-v1
review_guideline_version: reviewer-v1
transformation_guideline_version: retrieval-v1
source_schema_path: catalog/commerce_demo/generated/raw/schema.json
source_review_path: catalog/commerce_demo/review/orders.yml
source_review_commit: d638d62cc7aa92e4c52fce0ec3f0871b3e0b7170
generator_mode: live
generator_model: gpt-oss-120b
prompt_version: workflow-neutral-narrative-v2
---

# commerce_demo.orders — Orders

## Summary

Each row in the orders table captures a single customer order (grain = one row per order_id). The table stores UTC timestamps for creation (created_at) and last update (updated_at), a logical customer reference (customer_id) for joining to customers, a stable order identifier (order_id), the order status (pending, paid, shipped, cancelled) – with cancelled orders remaining present – and the total amount in VND. It is appropriate for daily order reporting, analysis of order volume and revenue, and can be joined to customers by customer_id. It is not suitable as a payment settlement source. Data is refreshed near real time.

## Grain and purpose

**Grain:** One row per order_id.
- Analyze order volume and revenue.

## Appropriate use

- Daily order reporting.
- Join an order to customers by customer_id.

## Inappropriate use

- Do not use as a payment settlement source.

## Columns

### `created_at` — Order created time

UTC timestamp recorded when the order was created.

- Technical type: `DateTime`
- Nullable: `false`
- Semantic type: `timestamp`
- Unit/timezone: `UTC`
- Null meaning: not_applicable
- Sensitivity: `internal`

### `customer_id` — Customer identifier

Identifier used for the logical join to customers.customer_id.

- Technical type: `UUID`
- Nullable: `false`
- Semantic type: `foreign_identifier`
- Unit/timezone: `not_applicable`
- Null meaning: not_applicable
- Sensitivity: `internal`
- Caveats:
  - The ClickHouse relation is logical and is not treated as an enforced foreign key.

### `order_id` — Order identifier

Stable technical identifier for one order.

- Technical type: `UUID`
- Nullable: `false`
- Semantic type: `identifier`
- Unit/timezone: `not_applicable`
- Null meaning: not_applicable
- Sensitivity: `internal`

### `order_status` — Order status

Current lifecycle state recorded for the order.

- Technical type: `LowCardinality(String)`
- Nullable: `false`
- Semantic type: `categorical`
- Unit/timezone: `not_applicable`
- Null meaning: not_applicable
- Sensitivity: `internal`
- Allowed values:
  - `cancelled`: Order has been cancelled but remains in the table.
  - `paid`: Order has been paid.
  - `pending`: Order is pending.
  - `shipped`: Order has been shipped.
- Caveats:
  - Transition rules require reviewer confirmation.

### `total_amount` — Order total amount

Order total recorded after discounts.

- Technical type: `Decimal(18, 2)`
- Nullable: `false`
- Semantic type: `monetary_amount`
- Unit/timezone: `VND`
- Null meaning: not_applicable
- Sensitivity: `internal`
- Caveats:
  - Tax, shipping, refund, and cancellation treatment require reviewer confirmation.

### `updated_at` — Order updated time

UTC timestamp of the latest recorded order update.

- Technical type: `DateTime`
- Nullable: `false`
- Semantic type: `timestamp`
- Unit/timezone: `UTC`
- Null meaning: not_applicable
- Sensitivity: `internal`

## Relationships and join risks

### orders_to_customers

Associates each order with the customer identifier that placed it.

- From: `orders` columns `customer_id`
- To: `customers` columns `customer_id`
- Join condition: `orders.customer_id = customers.customer_id`
- Cardinality: `many_to_one`
- Optional: `false`
- Row-count risk: `unknown`
- ClickHouse-enforced: `false`
- tbls relation: `orders.customer_id -> customers.customer_id`

## Business rules

### Cancelled orders remain present

A cancelled status does not imply that the order row is deleted.

## Time and unit semantics

- `created_at`: semantic type `timestamp`, unit/timezone `UTC`; UTC timestamp recorded when the order was created.
- `order_status`: semantic type `categorical`, unit/timezone `not_applicable`; Current lifecycle state recorded for the order.
- `total_amount`: semantic type `monetary_amount`, unit/timezone `VND`; Order total recorded after discounts.
- `updated_at`: semantic type `timestamp`, unit/timezone `UTC`; UTC timestamp of the latest recorded order update.

## Data quality and caveats

- Confirm order_id uniqueness before relying on one-row-per-order grain.
- Business ownership and refresh expectations require reviewer confirmation.

## Security

Not applicable — no table-level security instruction was supplied.

## Evidence

- `confirmed` `clickhouse_comment` — `catalog/commerce_demo/generated/raw/schema.json#tables.orders.columns.created_at`: Derived from the ClickHouse column comment.
- `confirmed` `clickhouse_comment` — `catalog/commerce_demo/generated/raw/schema.json#tables.orders.columns.customer_id`: Derived from the ClickHouse column comment.
- `confirmed` `clickhouse_comment` — `catalog/commerce_demo/generated/raw/schema.json#tables.orders.columns.order_id`: Derived from the ClickHouse column comment.
- `confirmed` `clickhouse_comment` — `catalog/commerce_demo/generated/raw/schema.json#tables.orders.columns.order_status`: Values are listed in the ClickHouse column comment.
- `confirmed` `clickhouse_comment` — `catalog/commerce_demo/generated/raw/schema.json#tables.orders.columns.total_amount`: Derived from the ClickHouse column comment.
- `confirmed` `clickhouse_comment` — `catalog/commerce_demo/generated/raw/schema.json#tables.orders.columns.updated_at`: Derived from the ClickHouse column comment.
- `confirmed` `clickhouse_comment` — `catalog/commerce_demo/generated/raw/schema.json#tables.orders.comment`: Derived from the ClickHouse table comment.
- `confirmed` `clickhouse_comment` — `catalog/commerce_demo/generated/raw/schema.json#tables.orders.comment`: Technical ClickHouse comment; business meaning still requires reviewer confirmation.
- `confirmed` `tbls_relation` — `catalog/commerce_demo/generated/raw/schema.json#relations.orders_to_customers`: Logical relation configured for tbls; cardinality requires data validation.
