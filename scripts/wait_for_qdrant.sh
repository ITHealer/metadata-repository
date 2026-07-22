#!/usr/bin/env bash
set -euo pipefail

MAX_ATTEMPTS="${QDRANT_WAIT_ATTEMPTS:-30}"
WAIT_SECONDS="${QDRANT_WAIT_INTERVAL_SECONDS:-3}"
BASE_URL="${QDRANT_URL:-http://localhost:6333}"
COMPOSE_PROJECT="${QDRANT_COMPOSE_PROJECT:-metadata-vector}"
READY_URL="${BASE_URL%/}/readyz"

for ((attempt = 1; attempt <= MAX_ATTEMPTS; attempt++)); do
  if curl --fail --silent --show-error "${READY_URL}" >/dev/null 2>&1; then
    printf 'Qdrant is ready (attempt %s/%s).\n' "${attempt}" "${MAX_ATTEMPTS}"
    exit 0
  fi

  if ((attempt < MAX_ATTEMPTS)); then
    printf 'Waiting for Qdrant (attempt %s/%s)...\n' "${attempt}" "${MAX_ATTEMPTS}"
    sleep "${WAIT_SECONDS}"
  fi
done

printf 'Qdrant did not become ready after %s attempts.\n' "${MAX_ATTEMPTS}" >&2
docker compose --project-name "${COMPOSE_PROJECT}" logs --tail=50 qdrant >&2 || true
exit 1
