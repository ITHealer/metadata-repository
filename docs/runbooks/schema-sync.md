# ClickHouse schema synchronization runbook

## PR-11 staged multi-database core

The `metadata scheduled-sync` command is the provider-neutral core for scheduled extraction. It does
not create a branch, commit, Pull Request, or notification. The production workflow wraps it with
separate, testable PR lifecycle commands and consumes only its stable JSON report.

Every source must opt in explicitly in `config/databases/<key>/database.yml`:

```yaml
enabled: true
scheduled_sync: true
tbls_dsn_env: TBLS_DSN_URGIFT
```

Keep the credential itself outside Git. For a local run, export the feature flag and every opted-in
profile's read-only DSN, then run:

```bash
export SCHEMA_SYNC_ENABLED=true
export TBLS_DSN_URGIFT='clickhouse://readonly:...'
make scheduled-sync SCHEMA_SYNC_RUN_ID=local-20260721
```

The command performs these safety gates in order:

1. Stop successfully when `SCHEMA_SYNC_ENABLED=false`.
2. Load all scheduled profiles and resolve every DSN before starting an external process.
3. Generate and lint every database in `build/schema-sync/staging/<run-id>/` with `tbls --no-deps`.
4. Enforce the database name and reject every table outside the allowlist; a missing allowlisted
   table is recorded as deletion drift for manual review.
5. Refresh reviewer drafts in staging only after every raw snapshot passes.
6. Publish changed raw and review files only after the complete multi-database preflight succeeds.

Inspect `build/schema-sync/report.json` for the machine-readable outcome and
`build/schema-sync/pr-body.md` for reviewer-facing impact. Neither artifact contains a DSN. A
`manual_cleanup_required` outcome means removed schema objects are still preserved in reviewer YAML
and must be resolved by a domain reviewer.

The staging root is intentionally restricted to the repository's `build/schema-sync/` tree because
each run directory is replaced before generation. Do not point it at a catalog or source directory.

## Production schedule and runner contract

`Scheduled Schema Sync` runs every day at 01:17 Asia/Ho_Chi_Minh (`17 18 * * *` in UTC) on a runner
with both `self-hosted` and `schema-sync` labels. The runner must provide Git, GitHub CLI, Docker with
Compose, Python 3, outbound GitHub access, and network reach to every scheduled ClickHouse source.

Configure:

- Repository variable `SCHEMA_SYNC_ENABLED=true` to allocate the scheduled job.
- Repository secret `METADATA_BOT_TOKEN` from a fine-grained bot identity with Contents and Pull
  Request write permissions.
- One read-only secret such as `TBLS_DSN_URCARD` for each profile whose `tbls_dsn_env` names it.

When onboarding another scheduled profile, add its named secret to the workflow job `env` mapping;
GitHub Actions cannot dynamically dereference a secret from a profile file.

The same `SCHEMA_SYNC_ENABLED` value reaches the CLI as a second independent gate. A manual dispatch
with `force_run=true` sets the effective value to true for that run only. It does not bypass missing
tools, credentials, allowlists, schema validation, or PR safety checks. The cron expression and
runner label are deployment configuration in workflow YAML, not `.env` settings.

Do not create a `.env` file in CI. Secrets are mapped directly into the job environment and are not
included in command arguments, reports, summaries, or commits.

## Single active PR lifecycle

Before extraction, automation queries open PRs targeting `main` with label
`automation:schema-sync`:

1. Zero matches: remain on `main`; create a branch only if the core reports a change.
2. One match: fetch its `automation/schema-sync-*` branch, check it out, and merge `origin/main`
   without rebase or force push. Existing reviewer and metadata-bot commits are preserved.
3. More than one match: fail before extraction and require an operator to close or relabel extras.

For a valid change, the publish command rechecks the worktree allowlist, creates one bot commit,
recomputes the PR body against `origin/main`, and pushes without force. A new PR is created as Draft
and labeled atomically. An existing PR receives the commit and cumulative body update, while its
reviewer-selected Draft/Ready state remains unchanged. Disabled and no-change reports create no
branch or commit.

If merging `main`, pushing, or updating GitHub encounters a conflict or concurrent change, the job
fails rather than resolving history automatically. Inspect the active branch and rerun after the
conflict or competing workflow is resolved.

## Fixture UAT and safe rollout

Run **Schema Sync UAT** manually from the Actions tab with `scenario=baseline`.
When the committed raw schema matches ClickHouse, the job exits successfully without creating a
branch or empty Pull Request.

The first run may start without `catalog/commerce_demo/generated/raw/schema.json`. In that case the
workflow compares the extracted schema with an internal empty baseline, creates reviewer drafts, and
opens the first Draft Pull Request. Missing committed output is an expected onboarding state, not a
CI error.

For UAT, select `scenario=additive_test`. The fixture adds `orders.channel` and the `order_events`
table inside the disposable ClickHouse container, then proves that tbls and draft generation produce
a reviewable diff. This fixture must never run against an external database.

Only after both manual cases pass, the remote runner is verified, and read-only secrets are present
should maintainers set repository variable `SCHEMA_SYNC_ENABLED=true`. The daily production job is
not allocated while that variable is absent or false.

## Source and output boundary

The UAT workflow starts the repository's synthetic ClickHouse fixture. Production uses only
explicitly scheduled profiles and their read-only remote DSNs. Both workflows may commit only:

- `catalog/*/generated/raw/**`
- `catalog/*/review/**`

Production reuses the single labeled automation PR; fixture UAT uses a separate
`automation/fixture-schema-sync-*` branch namespace.
Neither pushes to `main`. Generated structured and published documents remain handled by
`Metadata PR / pr-gate`.

## Reviewing the generated PR

1. Check the PR table summary for added, modified, and deleted tables.
2. Inspect raw tbls output; never edit it manually.
3. Complete each reviewer file listed under **Reviewer attention**.
4. Resolve orphaned columns/tables explicitly when the schema removed an object.
5. Run `make review-validate` until it passes.
6. Confirm the metadata bot generated only `catalog/*/generated/published/**`.
7. Request domain-owner approval before merge.

The production PR body records cumulative table impact and explicit manual-cleanup findings. The
fixture UAT body additionally records draft refresh and validation exit codes. A destructive change
still requires the reviewer to resolve retained orphan metadata before merge.

## Rollback and recovery

- Soft stop: set repository variable `SCHEMA_SYNC_ENABLED=false`.
- Hard stop: disable `Scheduled Schema Sync` in GitHub Actions.
- Duplicate labeled PRs: keep the intended PR, close or relabel every other match, then rerun.
- Merge conflict with `main`: resolve it manually on the automation branch; automation never rebases
  or force pushes reviewer history.
- Non-fast-forward push: inspect concurrent reviewer or metadata-bot commits, then rerun from a fresh
  checkout.
- Close the active automation PR to abandon its proposed catalog changes. ClickHouse is accessed
  read-only and is never modified by this pipeline.
