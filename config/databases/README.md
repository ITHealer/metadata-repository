# Database onboarding

Directory names are stable lowercase repository keys. `clickhouse_database` preserves the exact
case-sensitive ClickHouse database name.

A production database starts as a disabled profile with `tables: []`. Disabled profiles are visible
to `make catalog-check-all` but are skipped by automation and cannot run draft, generation, or
publishing commands. This is intentional: an empty tbls `include` list can be interpreted as “no
filter” by tools, which is unsafe for a large production database.

To enable a profile, the developer must obtain and verify:

1. The exact ClickHouse database name.
2. The exact table allowlist from the data owner; no wildcard.
3. Read-only connection details supplied through CI secrets or local environment variables.
4. Any reviewed logical relationships for allowlisted tables.

Then create `tbls.yml`, extract raw schema into `catalog/<key>/generated/raw`, generate reviewer YAML
templates, run the database-scoped checks, and only afterward set `enabled: true`. Never commit a
DSN, password, sampled production row, or inferred table name.
