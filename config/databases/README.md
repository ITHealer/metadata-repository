# Database onboarding

Directory names are stable lowercase repository keys. `clickhouse_database` preserves the exact
case-sensitive ClickHouse database name.

A production database starts as a disabled profile with `tables: []`. Disabled profiles are visible
to `make catalog-check-all` but are excluded from automatic generation, publishing, and indexing.
Explicit database-scoped developer commands remain available so onboarding can extract a schema,
create reviewer drafts, and validate them before activation. An empty tbls `include` list can be
interpreted as “no filter” by tools, so never extract until an explicit table allowlist is configured.

To enable a profile, the developer must obtain and verify:

1. The exact ClickHouse database name.
2. The exact table allowlist from the data owner; no wildcard.
3. Read-only connection details supplied through CI secrets or local environment variables.
4. Any reviewed logical relationships for allowlisted tables.

Then create `tbls.yml`, extract raw schema into `catalog/<key>/generated/raw`, generate reviewer YAML
templates, and run the database-scoped checks while the profile remains disabled. Only afterward set
`enabled: true` to opt into CI generation. Never commit a DSN, password, sampled production row, or
inferred table name.

The complete developer, CI/bot, and zero-tool reviewer procedure is documented in
[`docs/runbooks/database-onboarding-end-to-end.md`](../../docs/runbooks/database-onboarding-end-to-end.md).
