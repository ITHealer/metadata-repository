#!/usr/bin/env bash
set -euo pipefail

REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ACTION="${1:-}"
DATABASE="${DATABASE:-commerce_demo}"
DOC_PATH="${TBLS_DOC_PATH:-catalog/${DATABASE}/generated/raw}"
TBLS_CONFIG="config/databases/${DATABASE}/tbls.yml"
TBLS_COMMAND=(docker compose --profile tools run --rm tbls)

cd "${REPOSITORY_ROOT}"

case "${ACTION}" in
  doc)
    TBLS_DOC_PATH="${DOC_PATH}" "${TBLS_COMMAND[@]}" doc --config "${TBLS_CONFIG}" --rm-dist
    if [[ ! -s "${DOC_PATH}/schema.json" ]]; then
      printf 'tbls did not create %s/schema.json.\n' "${DOC_PATH}" >&2
      exit 1
    fi
    ;;
  lint)
    TBLS_DOC_PATH="${DOC_PATH}" "${TBLS_COMMAND[@]}" lint --config "${TBLS_CONFIG}"
    ;;
  diff)
    TBLS_DOC_PATH="${DOC_PATH}" "${TBLS_COMMAND[@]}" diff --config "${TBLS_CONFIG}"
    ;;
  *)
    printf 'Usage: %s {doc|lint|diff}\n' "$0" >&2
    exit 2
    ;;
esac
