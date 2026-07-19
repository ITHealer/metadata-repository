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
    docker compose exec -T clickhouse sh -ec \
      'clickhouse-client --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" \
      --database "$CLICKHOUSE_DB" --multiquery' \
      < tests/fixtures/schema_changes/additive.sql
    ;;
  *)
    printf 'Unknown schema sync scenario: %s\n' "${SCENARIO}" >&2
    exit 2
    ;;
esac
