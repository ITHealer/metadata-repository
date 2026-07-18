CREATE DATABASE IF NOT EXISTS commerce_demo;

CREATE TABLE IF NOT EXISTS commerce_demo.customers
(
    customer_id UUID COMMENT 'Stable identifier for one demo customer',
    full_name String COMMENT 'Display name; synthetic data used only by this demo',
    email String COMMENT 'Synthetic contact email classified as PII; always uses the .test domain',
    segment LowCardinality(String) COMMENT 'Business segment: retail, premium, or enterprise',
    created_at DateTime COMMENT 'UTC timestamp when the customer profile was created'
)
ENGINE = MergeTree
ORDER BY customer_id
COMMENT 'Customer dimension at one row per customer; contains synthetic PII-like fields.';

CREATE TABLE IF NOT EXISTS commerce_demo.orders
(
    order_id UUID COMMENT 'Stable identifier for one order',
    customer_id UUID COMMENT 'Customer that placed the order; logical join to customers.customer_id',
    order_status LowCardinality(String) COMMENT 'Current lifecycle state: pending, paid, shipped, or cancelled',
    total_amount Decimal(18, 2) COMMENT 'Order total in VND after discounts',
    created_at DateTime COMMENT 'UTC timestamp when the order was created',
    updated_at DateTime COMMENT 'UTC timestamp of the latest order update'
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(created_at)
ORDER BY (created_at, order_id)
COMMENT 'Order fact at one row per order_id; cancelled orders remain in the table.';

CREATE TABLE IF NOT EXISTS commerce_demo.order_items
(
    order_id UUID COMMENT 'Parent order; logical join to orders.order_id',
    line_number UInt16 COMMENT 'One-based line position within an order',
    product_code String COMMENT 'Synthetic product code captured when the order was placed',
    quantity UInt16 COMMENT 'Number of product units on this order line',
    unit_price Decimal(18, 2) COMMENT 'Price per unit in VND when the order was placed'
)
ENGINE = MergeTree
ORDER BY (order_id, line_number)
COMMENT 'Order detail fact at one row per order_id and line_number.';
