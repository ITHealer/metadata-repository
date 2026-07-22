#!/usr/bin/env bash
set -euo pipefail

REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCENARIO="${1:-baseline}"

cd "${REPOSITORY_ROOT}"

case "${SCENARIO}" in
  baseline)
    exit 0
    ;;
  additive_test)
    docker compose exec -T clickhouse clickhouse-client \
      --user demo \
      --password demo_password \
      --database commerce_demo \
      --multiquery \
      < tests/fixtures/schema_changes/additive.sql
    column_count="$(
      docker compose exec -T clickhouse clickhouse-client \
        --user demo \
        --password demo_password \
        --database commerce_demo \
        --query \
        "SELECT count() FROM system.columns WHERE database = 'commerce_demo' AND table = 'orders' AND name = 'channel'" \
        | tr -d '[:space:]'
    )"
    if [[ "${column_count}" != "1" ]]; then
      printf 'additive_test did not create commerce_demo.orders.channel\n' >&2
      exit 1
    fi
    ;;
  *)
    printf 'Unknown schema sync scenario: %s\n' "${SCENARIO}" >&2
    exit 2
    ;;
esac
