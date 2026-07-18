import json
import os
import subprocess
from typing import cast

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_CLICKHOUSE_INTEGRATION") != "1",
        reason="set RUN_CLICKHOUSE_INTEGRATION=1 to test the live fixture",
    ),
]


def query_clickhouse(sql: str) -> list[dict[str, object]]:
    command = [
        "docker",
        "compose",
        "exec",
        "-T",
        "clickhouse",
        "sh",
        "-ec",
        (
            'exec clickhouse-client --user "$CLICKHOUSE_USER" '
            '--password "$CLICKHOUSE_PASSWORD" --database "$CLICKHOUSE_DB" '
            '--format JSONEachRow --query "$1"'
        ),
        "clickhouse-query",
        sql,
    ]
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        pytest.fail(f"ClickHouse query failed:\n{result.stderr}")

    return [cast(dict[str, object], json.loads(line)) for line in result.stdout.splitlines()]


def test_fixture_has_exact_tables_and_documented_columns() -> None:
    tables = query_clickhouse(
        "SELECT name, comment FROM system.tables WHERE database = currentDatabase() ORDER BY name"
    )
    assert [row["name"] for row in tables] == ["customers", "order_items", "orders"]
    assert all(isinstance(row["comment"], str) and row["comment"].strip() for row in tables)

    columns = query_clickhouse(
        "SELECT table, name, comment FROM system.columns "
        "WHERE database = currentDatabase() ORDER BY table, position"
    )
    assert len(columns) == 16
    assert all(isinstance(row["comment"], str) and row["comment"].strip() for row in columns)


def test_fixture_has_deterministic_row_counts() -> None:
    counts = query_clickhouse(
        "SELECT table_name, row_count FROM ("
        "SELECT 'customers' AS table_name, count() AS row_count FROM customers "
        "UNION ALL SELECT 'order_items' AS table_name, count() AS row_count FROM order_items "
        "UNION ALL SELECT 'orders' AS table_name, count() AS row_count FROM orders"
        ") ORDER BY table_name"
    )
    assert counts == [
        {"table_name": "customers", "row_count": 5},
        {"table_name": "order_items", "row_count": 12},
        {"table_name": "orders", "row_count": 8},
    ]


def test_fixture_covers_business_edge_cases_without_real_pii() -> None:
    statuses = query_clickhouse(
        "SELECT order_status, count() AS row_count FROM orders "
        "GROUP BY order_status ORDER BY order_status"
    )
    assert statuses == [
        {"order_status": "cancelled", "row_count": 2},
        {"order_status": "paid", "row_count": 3},
        {"order_status": "pending", "row_count": 1},
        {"order_status": "shipped", "row_count": 2},
    ]

    pii_and_time_checks = query_clickhouse(
        "SELECT countIf(NOT endsWith(email, '.test')) AS invalid_email_count, "
        "toString(min(created_at)) AS first_created_at FROM customers"
    )
    assert pii_and_time_checks == [
        {"invalid_email_count": 0, "first_created_at": "2025-01-01 08:00:00"}
    ]

    amount_checks = query_clickhouse(
        "SELECT count() AS mismatched_order_count FROM ("
        "SELECT orders.order_id FROM orders INNER JOIN ("
        "SELECT order_id, sum(quantity * unit_price) AS calculated_amount "
        "FROM order_items GROUP BY order_id"
        ") AS item_totals USING (order_id) "
        "WHERE orders.total_amount != item_totals.calculated_amount"
        ")"
    )
    assert amount_checks == [{"mismatched_order_count": 0}]
