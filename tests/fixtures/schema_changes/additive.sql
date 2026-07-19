ALTER TABLE commerce_demo.orders
    ADD COLUMN IF NOT EXISTS channel LowCardinality(String)
    COMMENT 'Order acquisition channel: web, mobile, or partner'
    AFTER order_status;

CREATE TABLE IF NOT EXISTS commerce_demo.order_events
(
    event_id UUID COMMENT 'Stable identifier for one synthetic order event',
    order_id UUID COMMENT 'Order associated with this logical event stream',
    event_type LowCardinality(String) COMMENT 'Event type: created, paid, shipped, or cancelled',
    occurred_at DateTime COMMENT 'UTC timestamp when the event occurred'
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(occurred_at)
ORDER BY (order_id, occurred_at, event_id)
COMMENT 'Synthetic event fact at one row per order lifecycle event.';
