# Phase 2 production UAT record

This record separates verified evidence from production gates that still require external
credentials or data-owner decisions. A `PASS` row must have a reproducible command, workflow run,
or retained artifact. A `BLOCKED` row must not be used to justify enabling a production flag.

Last updated: 2026-07-22 (Asia/Ho_Chi_Minh).

## Current go/no-go state

| Runtime | Repository flag | Decision | Reason |
|---|---|---|---|
| Telegram | `TELEGRAM_NOTIFICATIONS_ENABLED=true` | GO | Local `pr_review`/`job_failed` delivery and the full failure listener passed. |
| Scheduled schema sync | `SCHEMA_SYNC_ENABLED=false` | NO-GO | Production DSNs and UrCard/UrGift allowlists are not provisioned. |
| Vector index apply | `INDEX_APPLY_ENABLED=false` | NO-GO | Gemini and Qdrant credentials are not provisioned; no live apply evidence exists. |

## PR-17A — production source onboarding

| Scenario | Status | Evidence / required result |
|---|---|---|
| Fixture baseline | PASS | [Schema Sync UAT run 29886654112](https://github.com/ITHealer/metadata-repository/actions/runs/29886654112) |
| Fixture additive change | PASS | [Schema Sync UAT run 29887427292](https://github.com/ITHealer/metadata-repository/actions/runs/29887427292) |
| Self-hosted runner and production wrapper | PASS | [Scheduled Schema Sync run 29890000042](https://github.com/ITHealer/metadata-repository/actions/runs/29890000042); wrapper passed but inspected zero scheduled profiles. |
| Three read-only DSNs | BLOCKED | `TBLS_DSN_COMMERCE_DEMO`, `TBLS_DSN_URCARD`, and `TBLS_DSN_URGIFT` are absent from Actions secrets. |
| UrCard allowlist | BLOCKED | Data owner must provide exact table names; current profile has `tables: []`. |
| UrGift allowlist | BLOCKED | Data owner must provide exact table names; current profile has `tables: []`. |
| Production no-change baseline | BLOCKED | Requires all scheduled profiles, DSNs, and runner network reach. |
| Comment/additive drift | BLOCKED | Must run only on an approved UAT source using a separate write-capable operator identity. |
| Create first Draft PR | BLOCKED | Requires a real supported schema change. |
| Reuse the same Draft PR | BLOCKED | Requires a second change before the first automation PR is closed. |
| Workflow `pr_review` created/updated | BLOCKED | Local delivery passed; workflow-level evidence requires the two PR lifecycle cases above. |

Do not enable the schedule until every `BLOCKED` row in this section is resolved and a named domain
reviewer is assigned for each production database.

## PR-17B — VectorDB live UAT

| Scenario | Status | Evidence / required result |
|---|---|---|
| Offline apply/idempotency/retry contract | PASS | `make verify`: 191 tests passed, 87.96% measured coverage. |
| Disabled workflow gate | PASS | [Apply Vector Index run 29890058105](https://github.com/ITHealer/metadata-repository/actions/runs/29890058105) was skipped while the flag was false. |
| Approved desired package | PASS | Local `manifest-v2`: 3 documents and 22 chunks on `a8e9cfa`. |
| Gemini credential | BLOCKED | `GEMINI_API_KEY` is empty locally and absent from Actions secrets. |
| Qdrant connection | BLOCKED | `QDRANT_URL` and `QDRANT_API_KEY` are empty locally and absent from Actions secrets. |
| Bootstrap 768-dimension cosine collection | BLOCKED | Requires the Qdrant credentials above. |
| Full initial apply | BLOCKED | Expected `applied`, `verified: true`, and 22 desired chunks for the current baseline. |
| No-op reapply | BLOCKED | Expected zero upsert/delete, successful retrieval, and no duplicate `index_done`. |
| Changed chunk | BLOCKED | Must change an approved UAT document through the reviewer/bot flow. |
| Removed chunk | BLOCKED | Must demote/remove only a dedicated UAT document, then restore it. |
| Live golden retrieval | BLOCKED | The uploaded `vector-retrieval-report.json` must pass. |
| Telegram `index_done` | BLOCKED | Must be emitted once after a changed, verified apply and retrieval pass. |

Manual `force_run=true` is the only allowed way to perform these live tests while the repository
flag remains false. Permanently enable `INDEX_APPLY_ENABLED` only after all rows pass.

## Notification evidence

| Scenario | Status | Evidence |
|---|---|---|
| Local sandbox `job_failed` | PASS | Telegram API accepted the validated event on 2026-07-22. |
| Local sandbox `pr_review` | PASS | Telegram API accepted the validated event on 2026-07-22. |
| Full `workflow_run` failure listener | PASS | [Metadata Failure Notification run 29890447224](https://github.com/ITHealer/metadata-repository/actions/runs/29890447224) |
| `index_done` | BLOCKED | Depends on PR-17B live apply and retrieval evidence. |

## Sign-off

Before changing either remaining production flag to `true`, record:

- operator and data-owner names;
- run URLs for baseline, change, reuse/no-op, and recovery cases;
- affected database/table or collection;
- rollback performed and its result;
- reviewer approval and timestamp.

The executable procedure is in
[`phase-2-production-validation.md`](../runbooks/phase-2-production-validation.md).
