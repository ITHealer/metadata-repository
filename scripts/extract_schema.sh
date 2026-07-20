#!/usr/bin/env bash
set -euo pipefail

REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ACTION="${1:-}"
DOC_PATH="${TBLS_DOC_PATH:-catalog/commerce_demo/generated/raw}"
TBLS_COMMAND=(docker compose --profile tools run --rm tbls)

cd "${REPOSITORY_ROOT}"

case "${ACTION}" in
  doc)
    "${TBLS_COMMAND[@]}" doc --config config/databases/commerce_demo/tbls.yml --rm-dist
    if [[ ! -s "${DOC_PATH}/schema.json" ]]; then
      printf 'tbls did not create %s/schema.json.\n' "${DOC_PATH}" >&2
      exit 1
    fi
    ;;
  lint)
    "${TBLS_COMMAND[@]}" lint --config config/databases/commerce_demo/tbls.yml
    ;;
  diff)
    "${TBLS_COMMAND[@]}" diff --config config/databases/commerce_demo/tbls.yml
    ;;
  *)
    printf 'Usage: %s {doc|lint|diff}\n' "$0" >&2
    exit 2
    ;;
esac
