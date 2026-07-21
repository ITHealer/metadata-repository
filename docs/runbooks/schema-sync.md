# ClickHouse schema synchronization runbook

## Safe rollout

The workflow is manual-first. Run **Schema Sync** from the Actions tab with `scenario=baseline`.
When the committed raw schema matches ClickHouse, the job exits successfully without creating a
branch or empty Pull Request.

The first run may start without `catalog/commerce_demo/generated/raw/schema.json`. In that case the
workflow compares the extracted schema with an internal empty baseline, creates reviewer drafts, and
opens the first Draft Pull Request. Missing committed output is an expected onboarding state, not a
CI error.

For UAT, select `scenario=additive_test`. The fixture adds `orders.channel` and the `order_events`
table inside the disposable ClickHouse container, then proves that tbls and draft generation produce
a reviewable diff. This fixture must never run against an external database.

Only after both manual cases pass should maintainers set repository variable
`ENABLE_SCHEMA_SYNC=true`. The weekday schedule remains disabled when the variable is absent or
false.

## Source and output boundary

The MVP starts the repository's synthetic ClickHouse fixture. It does not connect to production.
The workflow may commit only:

- `catalog/*/generated/raw/**`
- `catalog/*/review/**`

It creates a timestamped automation branch and Draft Pull Request; it never pushes to `main`.
Generated published documents are handled later by `Metadata PR / pr-gate`.

## Reviewing the generated PR

1. Check the PR table summary for added, modified, and deleted tables.
2. Inspect raw tbls output; never edit it manually.
3. Complete each reviewer file listed under **Reviewer attention**.
4. Resolve orphaned columns/tables explicitly when the schema removed an object.
5. Run `make review-validate` until it passes.
6. Confirm the metadata bot generated only `catalog/*/generated/published/**`.
7. Request domain-owner approval before merge.

The draft refresh and validation exit codes are recorded in the PR body. A non-zero code is expected
for destructive schema drift that needs human cleanup; it is not permission to merge an invalid
review contract.

## Production follow-up

Production ClickHouse access is deliberately out of scope for this MVP. Before enabling it, use a
read-only allowlisted account, a network-restricted self-hosted runner, database allowlists, query
timeouts, and an audited credential-rotation owner.
