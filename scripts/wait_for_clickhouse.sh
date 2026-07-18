#!/usr/bin/env bash
set -euo pipefail

REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MAX_ATTEMPTS="${CLICKHOUSE_WAIT_ATTEMPTS:-30}"
WAIT_SECONDS="${CLICKHOUSE_WAIT_INTERVAL_SECONDS:-3}"

cd "${REPOSITORY_ROOT}"

for ((attempt = 1; attempt <= MAX_ATTEMPTS; attempt++)); do
  if docker compose exec -T clickhouse sh -ec \
    'exec clickhouse-client --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" --database "$CLICKHOUSE_DB" --query "SELECT 1"' \
    >/dev/null 2>&1; then
    printf 'ClickHouse is ready (attempt %s/%s).\n' "${attempt}" "${MAX_ATTEMPTS}"
    exit 0
  fi

  if ((attempt < MAX_ATTEMPTS)); then
    printf 'Waiting for ClickHouse (attempt %s/%s)...\n' "${attempt}" "${MAX_ATTEMPTS}"
    sleep "${WAIT_SECONDS}"
  fi
done

printf 'ClickHouse did not become ready after %s attempts.\n' "${MAX_ATTEMPTS}" >&2
docker compose logs --tail=50 clickhouse >&2 || true
exit 1
