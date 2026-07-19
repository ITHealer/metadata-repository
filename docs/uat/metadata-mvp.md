# Metadata MVP UAT record

This record separates reproducible evidence from environment-dependent checks. A check is never
marked passed merely because its code path is covered by a mock.

## Scope and environment

- Repository: `ITHealer/metadata-repository`
- Local environment: macOS, Python project virtual environment, Docker Desktop
- Gateway contract: OpenAI-compatible LiteLLM endpoint at `https://ai-gateway.dev/v1`
- Default model alias: `gpt-5.4-nano`
- Prompt version: `approved-narrative-v1`

## Evidence matrix

| Scenario | Command or evidence | Result | What it proves |
|---|---|---|---|
| Offline quality gates | `make verify` | Pass | Lint, types, coverage, CLI, and reviewer validation |
| Deterministic publication | `make knowledge-check` twice | Pass, byte-identical | Preflight, Markdown, chunks, and idempotency |
| Approved retrieval | `make retrieval-smoke` | Pass, 10/10 questions | Approved-only chunks retain required facts |
| ClickHouse/tbls baseline | `make db-reset db-up schema-check` | Pass during PR-08 UAT | Live fixture can produce and validate raw schema |
| Additive schema change | `tests/e2e/test_metadata_mvp.py` plus PR-08 fixture | Pass | New table is drafted and changed table returns to review |
| Invalid reviewer column | `tests/e2e/test_metadata_mvp.py` | Pass | Preflight blocks unknown columns before output |
| Live gateway protocol | `tests/unit/test_openai_compatible_generator.py` | Pass with mock HTTP transport | Endpoint/model routing, structured output, retries, and fact locks |
| Live gateway credential | Manual `Live LLM UAT` workflow | Pending external prerequisite | Real gateway authentication and model availability |
| Human commit to bot commit | Metadata PR with bot secret | Pending repository setup | Token permissions, bot loop prevention, and latest-SHA checks |
| Approved live narrative | Approved reviewer PR plus manual workflow | Pending domain approval | Real model output passes the same validator and chunker |

## Automated end-to-end scenarios

`tests/e2e/test_metadata_mvp.py` covers three stable scenarios without external services:

1. Happy path: approved in-memory review documents become validated chunks, an approved-only
   manifest, and a retrieval report with a 100% top-three document hit rate.
2. Schema change: adding `orders.channel` and a new `order_events` table refreshes the affected
   reviewer draft and creates the new one without overwriting human metadata.
3. Guardrail: a reviewer reference to `not_a_real_column` raises `unknown_column`; the publication
   directory is not created.

The gateway contract suite additionally verifies that an approved response may change only
narrative fields. Technical identifiers, type, nullability, unit, join condition, cardinality,
evidence, status, and version provenance remain equal to the deterministic baseline.

## Run the remaining live check

Repository administration is required once:

1. Add Actions secret `OPENAI_API_KEY`.
2. Add Actions variable `OPENAI_BASE_URL=https://ai-gateway.dev/v1`.
3. Add Actions variable `ENABLE_LIVE_LLM_UAT=true`.
4. Open **Actions → Live LLM UAT → Run workflow**.
5. Select `gpt-5.4-nano` and `json_schema` unless the gateway model requires `json_object`.
6. Download `live-metadata-uat-<run-id>` and inspect all Markdown before accepting the evidence.

The current committed documents are `needs_review`, so this run exercises the conservative
summary-only path. To exercise approved narrative generation, first obtain domain approval and
promote reviewer YAML in a normal metadata Pull Request. Do not edit generated Markdown or alter
status in a temporary CI script.

## Acceptance decision

The deterministic MVP, safety guardrails, workflow contracts, and mock gateway integration are
release-ready. Production enablement remains conditional on the three explicit external checks
above: gateway credential, bot credential, and human approval. Until they pass, keep live generation
manual and keep schema sync scheduling disabled.
