# Pull Request Plan — Scheduled Schema Sync, Telegram Notifications, and Vector Indexing

**Status:** Implementation plan only — no production code is delivered by this document
**Baseline:** `main` at `f37e7de`
**Continues:** [PR_PLAN.md](./PR_PLAN.md), after PR-10
**Planned PRs:** PR-11 through PR-17

## 1. Target outcome

The phase extends the existing Git-centric metadata review loop without replacing its current
ownership boundaries:

```text
Scheduled runner
  -> extract every scheduled/enabled ClickHouse database into staging
  -> validate and compare table-level technical schemas
  -> no change: exit successfully without a commit or Pull Request
  -> change: refresh affected reviewer drafts
  -> create one schema-sync Draft PR, or update the existing one
  -> notify reviewers through Telegram

Reviewer
  -> edits catalog/<database>/review/<table>.yml
  -> approves through the existing status-only promotion flow
  -> merges the Pull Request

Post-merge index workflow
  -> loads promoted structured candidates
  -> builds deterministic chunks and a desired index manifest
  -> embeds and applies only changed chunks to the vector database
  -> verifies the resulting knowledge base
  -> notifies index_done through Telegram

Any failed monitored workflow
  -> sends job_failed through Telegram
```

Only the reviewer step remains manual. Scheduled extraction, PR lifecycle, candidate generation,
indexing, and notifications are automated.

## 2. Decisions that apply to every PR

### 2.1 Artifact ownership remains unchanged

```text
catalog/<database>/generated/raw/         tbls-owned technical source
catalog/<database>/review/                human-owned business metadata
catalog/<database>/generated/structured/  machine-readable promoted candidate
catalog/<database>/generated/published/   reviewer-readable Markdown preview
build/                                    local/CI artifacts, never committed
```

Approved Markdown is not moved to another directory. Approval updates the same document to
`document_status: approved` and `index_eligible: true`. Indexing consumes structured candidates,
not Markdown.

### 2.2 Schema detection uses tbls once per scheduled database

The initial implementation does not add a second ClickHouse schema fingerprint reader. tbls runs
once per scheduled database into a staging directory, and the application compares the staged
`schema.json` with the committed `schema.json` by table.

This means:

- tbls runs for each scheduled database, even when the final diff is empty;
- only byte-different raw files are written;
- only added or modified tables have reviewer drafts refreshed;
- deleted tables/columns remain explicit manual-cleanup findings;
- a future fast pre-check can be added only if measured runtime justifies a second schema reader.

### 2.3 Scheduled extraction is preflight-first

All databases are generated and validated in `build/schema-sync/<run-id>/` before the working
catalog is changed. If any database fails, no bot commit or Pull Request is created. The clean CI
checkout may contain staged files, but Git never publishes a partial result.

### 2.4 Runtime flags do not define the GitHub cron expression

The local or self-hosted process reads flags from `.env`; GitHub Actions maps repository variables
to the same environment names. The actual GitHub schedule stays in workflow YAML because GitHub
evaluates workflow triggers before a runner starts.

Required flags:

```dotenv
SCHEMA_SYNC_ENABLED=false
SCHEMA_SYNC_OPEN_PR=true
TELEGRAM_NOTIFICATIONS_ENABLED=false
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_THREAD_ID=
TELEGRAM_TIMEOUT_SECONDS=10
INDEX_APPLY_ENABLED=false
```

### 2.5 Indexing is idempotent

The existing `chunk_id` format remains stable. A new deterministic `body_hash` identifies the
embedding text and index-relevant payload. Re-running the same desired manifest must cause zero
embedding, upsert, or delete calls.

### 2.6 A successful build is not yet an updated knowledge base

`index_done` is emitted only after the vector store apply and post-apply verification succeed.
Building or uploading `manifest.json` is not sufficient.

### 2.7 Common Definition of Done

Every implementation PR must satisfy all applicable items:

- Unit and contract tests are delivered in the same PR.
- `make lint`, `make typecheck`, and the scoped test suite pass.
- External HTTP/ClickHouse/VectorDB calls are mocked in the default test suite.
- Live UAT is manual or environment-gated.
- No DSN, API token, chat ID, production row, or credential-bearing command is logged.
- CLI failures return non-zero; disabled/no-change paths return zero with a structured reason.
- Files outside each workflow's explicit allowlist cause failure before Git commit.
- README/runbook changes describe enablement, rollback, and recovery.

## 3. Shared contracts introduced in this phase

### 3.1 Scheduled sync report

The schema-sync command writes `build/schema-sync/report.json` and prints a concise summary. The
report is the only data passed from the core use case to PR and notification steps.

Conceptual contract:

```json
{
  "format_version": "schema-sync-report-v1",
  "run_id": "github-run-id-or-local-id",
  "outcome": "disabled|noop|changed|manual_cleanup_required|failed",
  "databases": [
    {
      "key": "commerce_demo",
      "added": ["order_events"],
      "modified": ["orders"],
      "deleted": [],
      "raw_changed_paths": [
        "catalog/commerce_demo/generated/raw/orders.md",
        "catalog/commerce_demo/generated/raw/schema.json"
      ],
      "review_paths": ["catalog/commerce_demo/review/orders.yml"]
    }
  ],
  "warnings": [],
  "manual_cleanup": []
}
```

Rules:

- Lists are sorted for deterministic output.
- `noop` contains no changed paths.
- A deletion is present in the report even though reviewer-owned YAML is not deleted.
- The report never contains a DSN or environment-variable value.

### 3.2 Notification event

Conceptual common fields:

```json
{
  "event_version": "notification-v1",
  "event_type": "pr_review|index_done|job_failed",
  "event_id": "deterministic-id",
  "repository": "owner/repository",
  "branch": "branch-name",
  "commit": "git-sha",
  "workflow": "workflow-name",
  "run_url": "https://github.com/.../actions/runs/..."
}
```

Event-specific payloads provide PR URL and changed tables, index counts and manifest hash, or
failed workflow/job details. Telegram formatting is an adapter concern; application code receives
a validated event.

### 3.3 Index package

```text
build/index/
├── chunks.jsonl
├── manifest.json
├── actions.jsonl
├── retrieval-report.json
└── apply-summary.json
```

- `chunks.jsonl`: complete approved desired chunk payload.
- `manifest.json`: complete desired snapshot plus source commit and manifest hash.
- `actions.jsonl`: created/updated/removed/unchanged diff for audit.
- `retrieval-report.json`: retrieval quality result.
- `apply-summary.json`: actual VectorDB apply counts and verification result.

## 4. PR-11 — Staged, multi-database scheduled sync core

**Branch:** `codex/feat-pr-11-scheduled-schema-sync-core`
**Title:** `feat(schema): add staged multi-database scheduled sync`
**Depends on:** PR-01 through PR-10
**Estimated size:** Large
**Primary risk:** accidentally publishing a partial or out-of-scope schema

### Goal

Provide one provider-neutral CLI command that discovers scheduled databases, generates tbls output
into staging, validates every result, computes a deterministic change report, and refreshes the
working catalog without opening a Pull Request.

### Task 11.1 — Extend database profile scheduling configuration

**Files:**

```text
src/metadata_pipeline/domain/catalog.py
src/metadata_pipeline/io/database_profile.py
config/databases/*/database.yml
config/databases/README.md
tests/unit/test_catalog.py
```

**Implementation:**

- Add strict profile fields with safe defaults:
  - `scheduled_sync: false`;
  - `tbls_dsn_env: null`.
- Require `tbls_dsn_env` when `scheduled_sync: true`.
- Continue using `enabled` as the boundary for generation/index participation.
- Scheduled discovery selects profiles where both `enabled` and `scheduled_sync` are true.
- Store only the environment-variable name in Git; never store the DSN.
- Keep `commerce_demo` usable for fixture UAT without implying that it is a production source.

**Tests:**

- Reject scheduled profiles without an allowlist.
- Reject scheduled profiles without `tbls.yml` or `tbls_dsn_env`.
- Reject an invalid environment-variable name.
- Confirm disabled/non-scheduled profiles are excluded.

### Task 11.2 — Add the schema documenter port

**Files:**

```text
src/metadata_pipeline/ports/schema_documenter.py
src/metadata_pipeline/ports/__init__.py
tests/unit/test_scheduled_schema_sync.py
```

**Implementation:**

- Define a small port that accepts a validated catalog context, a secret supplied at runtime, and a
  staging output path.
- Return an observable result containing exit status and generated paths, not raw process output
  containing secrets.
- Keep subprocess, Docker, and tbls details out of application modules.

### Task 11.3 — Implement the tbls Docker adapter

**Files:**

```text
src/metadata_pipeline/adapters/schema/tbls_runner.py
scripts/extract_schema.sh
docker-compose.yml
tests/unit/test_tbls_runner.py
```

**Implementation:**

- Reuse the pinned tbls image.
- Run the tool service with `--no-deps` for a remote source so it does not start the local
  ClickHouse fixture.
- Pass `TBLS_DSN` and `TBLS_DOC_PATH` through the child environment, not command arguments.
- Build subprocess arguments as a sequence; do not use `shell=True`.
- Run `tbls doc --rm-dist` against staging, followed by `tbls lint`.
- Redact environment-variable values from errors and logs.
- Preserve the current local fixture path for manual/integration tests.

**Tests:**

- Verify the exact argv structure without executing Docker.
- Verify `--no-deps`, pinned config path, and staging output.
- Verify DSN absence and non-zero tbls exits produce actionable configuration/runtime errors.
- Verify captured errors do not include the credential value.

### Task 11.4 — Extend table-level schema comparison

**Files:**

```text
src/metadata_pipeline/application/schema_sync_summary.py
src/metadata_pipeline/domain/hashing.py
tests/unit/test_schema_sync_summary.py
```

**Implementation:**

- Reuse `TblsSchemaSource` and `table_schema_hash` as the comparison source.
- Detect added, modified, and deleted tables.
- Treat a relation change as a modification of both participating tables.
- Expose structured data separately from Markdown rendering.
- Support a missing committed schema as an empty baseline for first onboarding.

**Tests:**

- Table comment, column type, nullable, column comment, and relation changes are detected.
- Reordering deterministic schema fields produces no false change.
- Added/deleted tables are sorted and reported once.

### Task 11.5 — Implement the scheduled-sync application service

**Files:**

```text
src/metadata_pipeline/application/scheduled_schema_sync.py
src/metadata_pipeline/io/schema_sync_report_json.py
src/metadata_pipeline/cli.py
tests/unit/test_scheduled_schema_sync.py
```

**Implementation sequence:**

1. Load runtime settings without overriding already exported CI variables.
2. If `SCHEMA_SYNC_ENABLED=false`, write a disabled report and return zero before resolving DSNs.
3. Discover scheduled profiles in deterministic key order.
4. Resolve each profile's DSN environment variable; fail before calling tbls if any are absent.
5. Generate every database into its own staging directory.
6. Parse and validate every staged `schema.json` against database name and table allowlist.
7. Compare committed and staged schemas and construct one in-memory report.
8. If all database reports are no-op, write the report and leave `catalog/` untouched.
9. If changed, copy only byte-different generated raw files using atomic per-file writers; delete
   generated-only raw orphans that tbls removed.
10. Run the existing deterministic draft refresh after all raw preflight succeeds. Unaffected
    reviewer files must remain byte-identical.
11. Write `build/schema-sync/report.json` and a PR-body Markdown summary.

No Git branch, commit, PR, or Telegram call belongs in this application service.

### Task 11.6 — Add the CLI and Make targets

**Files:**

```text
src/metadata_pipeline/cli.py
Makefile
scripts/metadata
README.md
tests/unit/test_cli.py
```

**Command:**

```text
metadata scheduled-sync
  --repository-root .
  --staging-root build/schema-sync
  --report build/schema-sync/report.json
  --pr-body build/schema-sync/pr-body.md
```

**Exit behavior:**

| Outcome | Exit |
|---|---:|
| disabled | 0 |
| no change | 0 |
| changed and valid | 0 |
| changed with manual cleanup required | 0, report records manual action |
| missing secret, tbls error, invalid schema, unsafe path | non-zero |

Manual cleanup must not be hidden as a success message; it is a successful automation run whose PR
still requires a human.

### Task 11.7 — Contract and E2E tests

**Files:**

```text
tests/contract/test_scheduled_schema_sync.py
tests/e2e/test_scheduled_schema_sync.py
tests/fixtures/schema_changes/**
```

**Scenarios:**

- Disabled before any external dependency is constructed.
- No schema change.
- One changed table while all other raw/reviewer files remain byte-identical.
- New table and new reviewer draft.
- Added column preserves existing business fields and returns status to `needs_review`.
- Deleted column/table produces manual-cleanup entries and keeps reviewer YAML.
- Second database fails after the first staged successfully; catalog remains unpublished.
- Same inputs produce byte-identical report and files.

### PR-11 acceptance criteria

- The command supports more than one scheduled database without hardcoded keys.
- All staged schemas are validated before catalog writes begin.
- No-change and disabled runs are clean no-ops.
- A change report contains exact database/table/path information for later workflow steps.
- No GitHub or Telegram dependency exists in the core use case.

### Rollback

- Set `SCHEMA_SYNC_ENABLED=false`.
- Revert PR-11; existing manual fixture commands and metadata PR workflow remain available.
- Raw/review files are still Git-versioned, so an accidental bot commit can be reverted normally.

## 5. PR-12 — Daily runtime and single active schema-sync PR

**Branch:** `codex/feat-pr-12-schema-sync-runtime`
**Title:** `feat(automation): schedule schema sync and reuse active PR`
**Depends on:** PR-11
**Estimated size:** Medium
**Primary risk:** overwriting reviewer work on an existing automation branch

### Goal

Run the PR-11 command daily on a runner that can reach ClickHouse, then create one Draft PR or push a
new commit to the existing schema-sync PR.

### Task 12.1 — Separate fixture UAT from production schedule

**Files:**

```text
.github/workflows/schema-sync.yml
.github/workflows/schema-sync-uat.yml
tests/contract/test_schema_sync_workflow.py
```

**Implementation:**

- Move `baseline`/`additive_test`, local ClickHouse startup, and Docker cleanup to the manual UAT
  workflow.
- Keep production `schema-sync.yml` focused on remote configured databases.
- Production schedule runs daily at a non-peak minute in `Asia/Ho_Chi_Minh`.
- Retain `workflow_dispatch` for controlled manual runs.
- Use a dedicated self-hosted runner label with network reach to ClickHouse.
- Keep `concurrency.group: schema-sync` and do not cancel an in-progress sync.

### Task 12.2 — Add two-layer feature gating

**Files:**

```text
.env.example
.github/workflows/schema-sync.yml
docs/runbooks/schema-sync.md
```

**Implementation:**

- Repository variable `SCHEMA_SYNC_ENABLED` prevents scheduled runner allocation at the job `if`.
- The same value is exported as process environment for the CLI's independent runtime gate.
- Manual dispatch may expose an explicit `force_run` boolean. For that invocation only, the
  workflow sets the effective process flag to true. It bypasses the disabled flag, but never
  bypasses missing secrets, scope validation, or safety checks.
- The cron expression stays in YAML and is documented as not configurable through `.env`.

### Task 12.3 — Define repository secrets and runner contract

**Configuration:**

```text
METADATA_BOT_TOKEN                 repository secret
TBLS_DSN_<DATABASE_KEY>            repository/environment secret per scheduled DB
SCHEMA_SYNC_ENABLED                repository variable
SCHEMA_SYNC_RUNNER_LABEL           documented deployment label, not a runtime secret
```

**Implementation:**

- Use a fine-grained bot token with repository contents and Pull Request permissions required by
  the existing bot workflow.
- Do not write a generated `.env` file in CI. Export individual secret values directly to the step.
- Require the runner to have Docker, Git, Python, the GitHub CLI, and network reach to ClickHouse.
- Add a preflight step that reports missing tools without printing environment values.

### Task 12.4 — Resolve an existing schema-sync PR before extraction

**Implementation sequence:**

1. Checkout `main` with full Git history.
2. Query open PRs with label `automation:schema-sync`.
3. If more than one exists, fail and require operator cleanup.
4. If one exists, fetch and checkout its head branch before scheduled extraction. This ensures the
   next draft refresh sees and preserves reviewer changes already pushed to that branch.
5. If none exists, remain on `main` and reserve a new branch name only after a change is found.

Never use a force push. If the existing branch cannot incorporate current `main` safely, fail and
send a later `job_failed` event instead of resolving conflicts automatically.

### Task 12.5 — Create or update the Draft PR

**Implementation:**

- Run `metadata scheduled-sync` and parse only its validated JSON report.
- For disabled/no-op reports, stop without a commit.
- Enforce the write allowlist:
  - `catalog/*/generated/raw/**`;
  - `catalog/*/review/**`.
- Create one bot commit when the allowlist has a diff.
- New PR:
  - create `automation/schema-sync-<run-id>`;
  - push branch;
  - create Draft PR;
  - add label `automation:schema-sync`;
  - request configured reviewers or rely on CODEOWNERS.
- Existing PR:
  - push the commit to its current branch;
  - update the PR summary or add one bot comment with the latest change set;
  - do not change ready/draft state chosen by a reviewer.
- Recompute the PR summary against `main` so it describes the cumulative open PR, not only the
  newest run.

### Task 12.6 — Preserve the existing Metadata PR loop

**Implementation:**

- A schema-sync commit changes only raw/review inputs, so the existing Metadata PR workflow enters
  `generate` mode.
- Its candidate bot commit changes only structured/published output, then re-enters `validate`
  mode.
- Add contract coverage for an updated schema-sync PR receiving both automation commits without an
  infinite loop.
- Never set `document_status: approved` in schema-sync automation.

### Task 12.7 — Workflow tests and UAT

**Tests:**

- Static workflow contract for schedule, runner labels, flags, allowlist, and absence of direct main
  pushes.
- Mocked GitHub CLI tests for zero, one, and multiple open schema-sync PRs.
- Live repository UAT:
  - first change creates one Draft PR;
  - reviewer edits a YAML file;
  - second change pushes to the same PR without losing the edit;
  - no-change run creates no commit;
  - conflict path fails without force push.

### PR-12 acceptance criteria

- Production schedule no longer starts the demo ClickHouse fixture.
- Scheduled sync can be disabled before runner allocation and inside the CLI.
- At most one schema-sync PR is active.
- Human changes on the PR branch are preserved.
- The workflow never pushes directly to `main` and never auto-merges.

### Rollback

- Set repository variable `SCHEMA_SYNC_ENABLED=false`.
- Disable the workflow in GitHub Actions for a hard infrastructure stop.
- Close the active automation PR; no production database is modified because access is read-only.

## 6. PR-13 — Telegram notification core and pr_review event

**Branch:** `codex/feat-pr-13-telegram-notifications`
**Title:** `feat(notifications): notify metadata review events via Telegram`
**Depends on:** Existing package foundation; may be developed in parallel with PR-11
**Estimated size:** Medium
**Primary risk:** leaking the bot token or spamming reviewers

### Goal

Provide one validated, testable notification boundary and send a Telegram reminder when a schema
sync PR is created or receives a new schema-sync commit.

### Task 13.1 — Add notification domain models

**Files:**

```text
src/metadata_pipeline/domain/notification.py
tests/unit/test_notification_models.py
```

**Implementation:**

- Define strict event types `pr_review`, `index_done`, and `job_failed` now so all later workflows
  share one versioned contract.
- Validate URL, non-empty repository/branch/commit fields, sorted change lists, and event-specific
  required values.
- Generate an event ID from stable non-secret fields.
- Keep Telegram-specific formatting out of domain models.

### Task 13.2 — Add Notifier port and settings

**Files:**

```text
src/metadata_pipeline/ports/notifier.py
src/metadata_pipeline/application/send_notification.py
src/metadata_pipeline/io/notification_settings.py
.env.example
tests/unit/test_notification_settings.py
```

**Implementation:**

- Load the nearest local `.env` without overriding CI-provided variables.
- Fail configuration when notifications are enabled but token/chat ID are absent.
- Disabled notification returns a structured skipped result without constructing an HTTP client.
- Support an optional Telegram topic/thread ID.

### Task 13.3 — Implement Telegram adapter

**Files:**

```text
src/metadata_pipeline/adapters/notification/telegram.py
tests/unit/test_telegram_notifier.py
```

**Implementation:**

- POST JSON to Telegram `sendMessage` over HTTPS.
- Prefer plain text, or HTML with strict escaping. Do not interpolate event data into a shell
  command.
- Enforce the message length and summarize long table lists with a count plus truncated preview.
- Retry a bounded number of times for HTTP 429 and temporary 5xx/network errors.
- Respect a short timeout.
- Never include the token in exception messages; redact Telegram endpoint paths in logs.
- Treat a final non-2xx response as a notification failure.

### Task 13.4 — Add CLI notification command

**Files:**

```text
src/metadata_pipeline/cli.py
tests/unit/test_cli.py
```

**Command:**

```text
metadata notify --event-file build/notifications/event.json
```

The workflow writes a validated event file rather than passing PR titles, branch names, or table
lists as shell arguments.

### Task 13.5 — Hook pr_review into Schema Sync

**Files:**

```text
.github/workflows/schema-sync.yml
tests/contract/test_schema_sync_workflow.py
```

**Implementation:**

- After a successful PR create/update, build a `pr_review` event containing:
  - action `created` or `updated`;
  - PR URL and number;
  - head branch and head SHA;
  - database/table changes;
  - workflow run URL.
- Send only when a new schema-sync commit was pushed.
- Use a hidden bot PR-comment marker keyed by the notified head SHA to suppress duplicate messages
  when the same workflow attempt is rerun.
- Record the marker only after Telegram accepts the message.
- Notification failure makes the notification step visible as failed but does not delete or roll
  back an already-created PR.

### Task 13.6 — Tests and Telegram sandbox UAT

**Tests:**

- Exact `created` and `updated` message templates.
- Special characters in branch/table names remain data, not formatting or shell syntax.
- Disabled path performs no HTTP call.
- Missing settings fail before HTTP.
- 429 uses retry information within configured limits.
- 400/401 fails without retrying indefinitely.
- Token never appears in captured logs.
- Same PR head SHA is not notified twice.

### PR-13 acceptance criteria

- Reviewers receive a message with PR URL, branch, changed database/tables, and run URL.
- The adapter is provider-specific; application code depends only on `Notifier`.
- All default tests are network-free.
- Disabling Telegram does not disable schema sync.

### Rollback

- Set `TELEGRAM_NOTIFICATIONS_ENABLED=false`.
- Revert workflow hook while retaining the notification module for later events.
- Rotate/revoke the BotFather token if exposure is suspected.

## 7. PR-14 — Centralized job_failed notification

**Branch:** `codex/feat-pr-14-failure-notifications`
**Title:** `feat(ops): alert failed metadata workflows via Telegram`
**Depends on:** PR-13
**Estimated size:** Small to medium
**Primary risk:** privileged `workflow_run` executing untrusted PR content

### Goal

Notify Telegram when a monitored workflow finishes with failure, timeout, or cancellation, even if
the failed workflow stopped before reaching its own notification step.

### Task 14.1 — Add the workflow_run listener

**Files:**

```text
.github/workflows/notify-failure.yml
tests/contract/test_notification_workflow.py
```

**Implementation:**

- Listen to `workflow_run: completed` for an explicit workflow allowlist:
  - `Schema Sync`;
  - `Metadata PR`;
  - `Index Manifest`/future `Apply Index`;
  - `Quality`;
  - `Live LLM UAT`.
- Run only for `failure`, `timed_out`, or `cancelled` conclusions.
- Give only `contents: read` and `actions: read` permissions.
- Explicitly checkout the default branch if package code is required. Never checkout the failed
  run's head branch, merge ref, artifacts, or cache.
- Do not include the notifier workflow itself in the monitored list.

### Task 14.2 — Build the failure event safely

**Implementation:**

- Pass GitHub context values through environment variables or a JSON-producing step; do not embed
  branch, title, or actor values inside shell source.
- Query the Actions jobs endpoint read-only to collect failed job names.
- Include workflow name, conclusion, branch, commit, actor, attempt, and run URL.
- Use `workflow run id + attempt + conclusion` as the event ID.

### Task 14.3 — Failure behavior

- Telegram delivery failure leaves the notification workflow failed and visible in Actions.
- There is intentionally no recursive Telegram alert for the notifier itself.
- The operations runbook states that GitHub Actions UI/email is the fallback when Telegram itself
  is unavailable.

### Task 14.4 — Tests and UAT

- Static security contract rejects `pull_request_target`, PR-head checkout, artifact execution, and
  write permissions.
- Forced failure from each monitored workflow produces one correctly linked message.
- Successful and skipped workflows produce no message.
- A retry attempt has a distinct event ID and may alert again if it also fails.

### PR-14 acceptance criteria

- Failures are reported independently of the failed job's progress.
- No untrusted PR code runs in the secret-bearing notifier context.
- Message links directly to the failed workflow run and identifies failed jobs.

### Rollback

- Disable or revert `notify-failure.yml`.
- Core schema, review, and index workflows remain unaffected.

## 8. PR-15 — Durable index handoff and chunk-level diff

**Branch:** `codex/feat-pr-15-index-handoff`
**Title:** `feat(index): add hash-based index handoff contract`
**Depends on:** Existing PR-09 index manifest; may be developed in parallel with PR-11/PR-13
**Estimated size:** Large
**Primary risk:** changing chunk identity or treating ephemeral CI state as the previous index

### Goal

Upgrade the current audit-only manifest into a deterministic desired-state package that a VectorDB
apply job can reconcile idempotently.

### Task 15.1 — Add body_hash without changing chunk_id

**Files:**

```text
src/metadata_pipeline/domain/published.py
src/metadata_pipeline/application/build_chunks.py
src/metadata_pipeline/domain/hashing.py
src/metadata_pipeline/validation/chunks.py
tests/unit/test_build_chunks.py
```

**Implementation:**

- Keep the existing ID: `<database>.<table>::<chunk_type>::<semantic_key>`.
- Compute `body_hash` from canonical embedding text and index-relevant payload.
- Exclude run-specific values that do not affect retrieval semantics unless they must be updated in
  VectorDB payload.
- Validate a 64-character lowercase SHA-256.
- Same structured candidate produces the same chunk ID and hash on every machine.

### Task 15.2 — Introduce chunk-level actions

**Files:**

```text
src/metadata_pipeline/domain/index.py
src/metadata_pipeline/application/index_changes.py
tests/unit/test_index_changes.py
```

**Implementation:**

- Preserve the existing document Git actions for audit compatibility.
- Add a separate chunk action model:
  - operation: `upsert`, `delete`, or `skip`;
  - reason: `created`, `updated`, `removed`, or `unchanged`;
  - chunk ID, old hash, new hash.
- Compare complete before/after desired manifests by chunk ID.
- Sort deletes and upserts deterministically.

### Task 15.3 — Build the previous desired snapshot from Git

The ignored `build/index/manifest.json` does not survive a fresh CI runner and cannot be the
production previous state.

**Files:**

```text
src/metadata_pipeline/adapters/git/catalog_revision.py
src/metadata_pipeline/application/catalog_chunks.py
tests/unit/test_catalog_revision.py
```

**Implementation:**

- Load configured profiles and structured candidate JSON at a supplied Git revision through
  read-only `git ls-tree`/`git show` adapter calls.
- Build the base manifest from `INDEX_BASE` and the desired manifest from the current checkout.
- Handle first run, deleted database directories, renamed files, and invalid historical candidate
  data with explicit errors.
- Keep Git subprocess details outside the manifest comparison use case.

### Task 15.4 — Version the manifest and index package

**Files:**

```text
src/metadata_pipeline/domain/index.py
src/metadata_pipeline/adapters/index/manifest.py
src/metadata_pipeline/io/chunk_jsonl.py
src/metadata_pipeline/io/index_actions_jsonl.py
```

**Implementation:**

- Introduce a new manifest format version because Chunk gains `body_hash`.
- Include source commit, generator/guideline versions already present in chunks, and a deterministic
  `manifest_hash` computed without recursively hashing itself.
- Write actions as JSONL and chunks as JSONL atomically.
- Validate duplicate chunk IDs across databases before any artifact is written.

### Task 15.5 — Add the index-package CLI

**Files:**

```text
src/metadata_pipeline/cli.py
Makefile
tests/unit/test_cli.py
```

**Command:**

```text
metadata build-index-package
  --base HEAD^
  --head HEAD
  --source-commit <sha>
  --output-dir build/index
```

The command performs candidate integrity checks, approved-only chunking, base/head manifest
construction, chunk action diff, and artifact writes as one preflighted operation.

### Task 15.6 — Update the post-merge workflow

**Files:**

```text
.github/workflows/index.yml
tests/contract/test_index_workflow.py
```

**Implementation:**

- Trigger on promoted structured/published changes on `main` as today.
- Build the complete index package.
- Run deterministic golden retrieval checks.
- Upload all audit artifacts with source SHA in the artifact name.
- Do not commit `build/**` back to `main`.
- Do not emit `index_done`; no VectorDB was updated in this PR.

### Task 15.7 — Tests

- Same manifest twice produces only skip/unchanged actions.
- Added table creates upserts.
- One changed column affects only the relevant column chunk and any overview/quality chunk whose
  content actually changed.
- Deleted table produces deletes for all of its previous chunks.
- Status changed from approved to needs-review removes the document from desired index.
- Tampered candidate or duplicate cross-database chunk ID blocks all artifact writes.
- Manifest/action/chunk ordering is deterministic.

### PR-15 acceptance criteria

- A fresh CI runner can compute before/after actions without relying on an ignored local manifest.
- Existing chunk IDs remain compatible.
- Every desired chunk carries a deterministic body hash.
- The package is auditable but does not claim that VectorDB has been updated.

### Rollback

- Revert to the PR-09 manifest workflow.
- No VectorDB mutation exists yet, so rollback affects only CI artifacts.

## 9. PR-16 — VectorDB apply and index_done notification

**Branch:** `codex/feat-pr-16-vector-index-apply`
**Title:** `feat(index): apply approved chunks to vector knowledge base`
**Depends on:** PR-13 and PR-15
**Estimated size:** Large
**Primary risk:** partial updates leaving stale or mixed embedding state

### Required decisions before implementation starts

- Confirm VectorDB provider and network location.
- Confirm embedding provider, model, dimension, and rate limits.
- Decide whether CI can reach VectorDB or a cluster CronJob must perform apply.
- Provision a non-production collection for contract and live UAT.

The default implementation path in this plan is Qdrant plus a Gemini embedding adapter, but ports
must keep providers replaceable.

### Task 16.1 — Add embedding and vector index ports

**Files:**

```text
src/metadata_pipeline/ports/embedder.py
src/metadata_pipeline/ports/vector_index.py
tests/unit/fakes/fake_embedder.py
tests/unit/fakes/fake_vector_index.py
```

**Interfaces:**

- `Embedder.embed_documents(texts)` for indexing.
- `Embedder.embed_query(text)` for retrieval.
- `VectorIndex.list_chunk_states()` returning chunk ID/body hash/payload identity.
- `VectorIndex.upsert(points)`.
- `VectorIndex.delete(point_ids)`.

Keep this separate from the existing `IndexStore`, whose responsibility is loading/saving manifest
snapshots.

### Task 16.2 — Add strict index runtime settings

**Files:**

```text
src/metadata_pipeline/io/index_settings.py
.env.example
tests/unit/test_index_settings.py
```

**Settings:**

```dotenv
INDEX_APPLY_ENABLED=false
EMBEDDING_PROVIDER=gemini
EMBEDDING_MODEL=gemini-embedding-001
EMBEDDING_DIMENSION=768
QDRANT_URL=
QDRANT_API_KEY=
QDRANT_COLLECTION=metadata__gemini_embedding_001__768
```

Validate that collection identity, embedding model, and dimension are consistent. A model or
dimension change must target a new collection, not mix vectors in the old one.

### Task 16.3 — Implement the Gemini embedder adapter

**Files:**

```text
src/metadata_pipeline/adapters/embedding/gemini.py
tests/unit/test_gemini_embedder.py
```

**Implementation:**

- Use the official SDK and pin the tested version.
- Use document and query task types appropriate to their purpose.
- Batch below verified provider input/token limits.
- Validate returned vector count and dimension.
- Normalize reduced-dimensional vectors if required by the verified model contract.
- Retry bounded transient errors; reject invalid/permanent errors.
- Mock all SDK calls in the default suite.

Provider signatures and limits must be verified from current official documentation during this
PR; examples in planning documents are not treated as executable API contracts.

### Task 16.4 — Implement the Qdrant adapter

**Files:**

```text
src/metadata_pipeline/adapters/index/qdrant.py
tests/unit/test_qdrant_vector_index.py
```

**Implementation:**

- Convert string chunk IDs to deterministic UUIDv5 point IDs with a fixed repository namespace.
- Store the original chunk ID and body hash in payload.
- Store database, table, chunk type, source review commit, schema hash, generator identity, and
  manifest hash as filterable payload.
- List existing managed points and their body hashes through paginated reads.
- Batch upserts/deletes within verified client limits.
- Do not delete points outside the configured collection/managed namespace.

### Task 16.5 — Add collection bootstrap as a separate command

**Files:**

```text
src/metadata_pipeline/application/bootstrap_vector_index.py
src/metadata_pipeline/cli.py
tests/unit/test_bootstrap_vector_index.py
```

**Implementation:**

- `metadata bootstrap-vector-index` creates the collection only when absent.
- Existing collection must match dimension and distance; mismatch fails instead of recreating or
  deleting data.
- Collection creation is not hidden inside every apply operation.
- Blue-green migration uses a new collection and an explicit retrieval-side alias/config switch.

### Task 16.6 — Implement apply-index use case

**Files:**

```text
src/metadata_pipeline/application/apply_index.py
src/metadata_pipeline/io/apply_summary_json.py
src/metadata_pipeline/cli.py
tests/unit/test_apply_index.py
```

**Algorithm:**

1. If `INDEX_APPLY_ENABLED=false`, return a disabled result before creating external clients.
2. Load and validate the complete desired index package.
3. Read current managed chunk ID/body hash state from VectorDB.
4. Compute created, updated, removed, and unchanged IDs from actual store state, not only Git diff.
5. Embed created/updated chunks in deterministic batches.
6. Upsert new/updated vectors and payloads.
7. Delete stale points only after required upserts succeed.
8. Re-read affected IDs and verify desired body hashes plus removal of deleted IDs.
9. Write `apply-summary.json` only with the actual operation counts and verification state.

If an upsert succeeds and a later delete fails, the run remains failed. A retry lists current store
state, skips already-correct upserts, and retries remaining actions. There is no false successful
manifest advance.

### Task 16.7 — Add post-apply retrieval verification

**Files:**

```text
src/metadata_pipeline/application/retrieval_evaluation.py
src/metadata_pipeline/adapters/index/qdrant_retriever.py
tests/contract/test_vector_retrieval.py
```

**Implementation:**

- Embed golden questions with query embedding semantics.
- Query the target collection and enforce configured top-k quality thresholds.
- Verify all returned points belong to the expected collection/model version.
- Treat retrieval verification failure as an apply workflow failure.

### Task 16.8 — Deploy apply runtime

Choose one wrapper while keeping the same CLI:

- CI job when the runner reaches Qdrant; or
- Kubernetes CronJob/pull-based job when Qdrant is cluster-internal.

For a Kubernetes wrapper:

- poll/check out the target `main` commit;
- run `build-index-package`, then `apply-index`;
- set `concurrencyPolicy: Forbid`;
- set retry and execution deadlines;
- inject secrets from Kubernetes Secret, not image or ConfigMap;
- exit zero on disabled/no-op and non-zero on any incomplete apply.

Airflow is not introduced unless the organization already operates it or the workflow later becomes
a multi-branch DAG requiring backfill/orchestration.

### Task 16.9 — Emit index_done

**Implementation:**

- Build `index_done` only after apply and retrieval verification pass.
- Include source commit, manifest hash, collection, document/chunk totals, actual upsert/delete/skip
  counts, and workflow run URL.
- Do not send for disabled or unchanged runs unless operators explicitly request heartbeat
  notifications later.
- Event ID uses collection plus manifest hash; a retry of the same successfully applied manifest is
  suppressed because it produces no actions.
- Any partial apply, embedding failure, VectorDB error, or smoke-test failure is handled by the
  centralized `job_failed` workflow instead.

### Task 16.10 — Tests and live UAT

**Offline tests:**

- Same manifest twice: second run performs no embedding/upsert/delete.
- One changed chunk: only that chunk is embedded and upserted.
- Removed chunk: exact deterministic point ID is deleted.
- Provider timeout retries within limits.
- Dimension mismatch fails before upsert.
- Partial batch failure does not produce `index_done`.
- Retry after partial upsert skips points already matching desired hashes.

**Live non-production UAT:**

- Bootstrap collection.
- Full initial index.
- Incremental one-table update.
- Delete/rollback test.
- Query golden questions.
- Change collection for a model/dimension migration and switch retrieval explicitly.

### PR-16 acceptance criteria

- Only promoted/approved chunks enter VectorDB.
- Apply is idempotent against actual VectorDB state.
- Partial failures are retriable and never reported as `index_done`.
- An unchanged rerun has zero provider calls except the state read/health check.
- Provider credentials never appear in logs or artifacts.

### Rollback

- Set `INDEX_APPLY_ENABLED=false`.
- Point retrieval back to the previous collection for a blue-green rollback.
- Rebuild the desired collection from a known Git commit/index package.
- Reverting code does not delete a collection automatically.

## 10. PR-17 — Production UAT, operations, and documentation

**Branch:** `codex/docs-pr-17-pipeline-operations`
**Title:** `docs(ops): document scheduled sync and index recovery`
**Depends on:** PR-12, PR-14, PR-16
**Estimated size:** Medium
**Primary risk:** declaring production readiness without live evidence

### Goal

Run and record the complete operational scenarios, remove stale documentation, and provide recovery
procedures before enabling schedules in production.

### Task 17.1 — Scheduled sync UAT record

Record evidence for:

- disabled schedule;
- no-change daily run;
- added column;
- modified comment/type;
- deleted column/table requiring manual cleanup;
- multiple databases in one run;
- one database connection failure with no PR;
- create a new PR;
- update the existing PR while preserving reviewer edits;
- merge and automatic branch cleanup.

### Task 17.2 — Notification UAT record

- Telegram bot is added to the intended chat/channel and allowed to post.
- `pr_review created` and `pr_review updated` include correct links/branch/table changes.
- Forced workflow failure emits `job_failed`.
- Successful VectorDB update emits one `index_done`.
- Notification disabled paths produce no message.
- Token rotation is tested without code changes.

### Task 17.3 — Index and recovery UAT

- Full initial index.
- No-op reapply.
- Incremental update and deletion.
- Retry after injected partial failure.
- Full rebuild from a selected Git commit.
- Blue-green collection rollback.
- Golden retrieval report retained with collection/model identity.

### Task 17.4 — Runbooks

**Files:**

```text
docs/runbooks/scheduled-schema-sync.md
docs/runbooks/telegram-notifications.md
docs/runbooks/vector-index-operations.md
docs/uat/metadata-phase-2.md
README.md
PR_PLAN.md
```

Document:

- enable/disable through repository variables and runtime environment;
- hard-disable a GitHub schedule;
- required runner/network/tool contract;
- DSN and Telegram/VectorDB secret rotation;
- active schema-sync PR conflict recovery;
- manual re-index/full rebuild;
- partial apply diagnosis;
- Telegram outage fallback;
- collection migration and rollback;
- ownership/escalation contacts.

### Task 17.5 — Fix known documentation drift

- `commerce_demo` is enabled in the current profile.
- Current committed candidates are promoted and index-eligible.
- The index build is no longer described as empty once the implementation changes.
- Distinguish deterministic fixture retrieval tests from live VectorDB UAT.

### PR-17 acceptance criteria

- Every live claim has a run URL/log/artifact reference and date.
- Operators can disable schema sync and index apply without a code deployment.
- Recovery instructions can rebuild the knowledge base from Git-owned structured candidates.
- No schedule is enabled for a production database until its allowlist, read-only DSN, runner
  network, and named reviewer are confirmed.

## 11. Dependency and delivery sequence

```text
Stream A — Schema automation
  PR-11 -> PR-12

Stream B — Notifications
  PR-13 -> PR-14

Stream C — Index contract
  PR-15

Convergence
  PR-13 + PR-15 -> PR-16
  PR-12 + PR-14 + PR-16 -> PR-17
```

Recommended merge order:

1. PR-11, PR-13, and PR-15 may be developed in parallel.
2. Merge PR-11 before PR-12.
3. Merge PR-13 before PR-14.
4. Merge PR-13 and PR-15 before PR-16.
5. Keep all production flags false through PR-16.
6. Complete PR-17 UAT before enabling the daily production schedule or VectorDB apply.

## 12. Issue/board task list

The following IDs can be copied directly into the project board:

```text
11.1 Profile scheduling fields
11.2 SchemaDocumenter port
11.3 tbls Docker adapter
11.4 Table-level schema comparison
11.5 Scheduled-sync application service
11.6 CLI and Make targets
11.7 Contract/E2E tests

12.1 Split production and fixture workflows
12.2 Two-layer feature gate
12.3 Secrets and runner contract
12.4 Existing PR resolution
12.5 Create/update Draft PR
12.6 Preserve Metadata PR bot loop
12.7 Workflow UAT

13.1 Notification event models
13.2 Notifier port and settings
13.3 Telegram adapter
13.4 Notify CLI
13.5 pr_review hook and deduplication
13.6 Telegram tests/UAT

14.1 workflow_run listener
14.2 Safe failure event construction
14.3 Failure behavior/fallback
14.4 Failure notification UAT

15.1 Chunk body_hash
15.2 Chunk-level actions
15.3 Git revision catalog source
15.4 Manifest/index-package version
15.5 Index-package CLI
15.6 Post-merge workflow update
15.7 Index contract tests

16.1 Embedder and VectorIndex ports
16.2 Index runtime settings
16.3 Gemini adapter
16.4 Qdrant adapter
16.5 Collection bootstrap command
16.6 Apply-index use case
16.7 Post-apply retrieval verification
16.8 Runtime deployment
16.9 index_done notification
16.10 Offline/live UAT

17.1 Scheduled sync evidence
17.2 Notification evidence
17.3 Index/recovery evidence
17.4 Runbooks
17.5 Documentation drift cleanup
```

## 13. Final end-to-end acceptance matrix

| Scenario | Required result |
|---|---|
| `SCHEMA_SYNC_ENABLED=false` | No ClickHouse/tbls call, no PR, exit zero |
| Scheduled DB has no change | No catalog write, no commit, no `pr_review` |
| One table changes | Exact raw diff; affected reviewer YAML returns to `needs_review` |
| New table | Raw docs plus reviewer draft; PR summary marks added |
| Column/table removed | Reviewer data retained; manual cleanup clearly listed |
| One of multiple DBs fails | No partial bot commit/PR; `job_failed` |
| Schema-sync PR already open | Push to the same branch/PR; preserve reviewer changes |
| Reviewer changes status only | Promote without LLM; Markdown body hash unchanged |
| Reviewer changes content while approving | Candidate stale; approval blocked |
| Merge approved metadata | Build complete desired approved-only index package |
| First VectorDB apply | Embed/upsert desired chunks and verify retrieval |
| Reapply same manifest | Zero embed/upsert/delete; no duplicate `index_done` |
| One chunk changes | Only that body hash is embedded/upserted |
| Chunk removed | Exact stale point deleted |
| Apply or smoke test fails | No `index_done`; centralized `job_failed` |
| Telegram disabled | Core workflows continue without Telegram HTTP calls |
