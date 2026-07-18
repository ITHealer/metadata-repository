# ClickHouse Metadata Review Loop

Small, testable implementation of the metadata workflow described in [PRD.md](./PRD.md).
The delivery sequence and acceptance criteria live in [PR_PLAN.md](./PR_PLAN.md).

The project uses GitHub Pull Requests as the review boundary and GitHub Actions as the automation
runtime. PR-01 provides only the repository foundation and quality gates; ClickHouse, `tbls`,
metadata generation, and indexing are added by later merge requests.

## Prerequisites

- Python 3.9–3.12.
- GNU Make.
- Git.
- Docker Engine with the Compose plugin.

## Local development

```bash
make install
make verify
```

Useful commands:

```bash
make help       # List supported commands
make format     # Apply Ruff fixes and formatting
make lint       # Check lint and formatting
make typecheck  # Run strict mypy checks
make test       # Run unit tests
make smoke      # Verify the CLI and Python runtime
```

The development commands always use `.venv`; this keeps local and CI behavior predictable.

## ClickHouse demo fixture

PR-02 provides a deterministic `commerce_demo` database. Start from a clean volume and validate
the complete fixture with:

```bash
make db-reset db-up db-check
```

The fixture contains only synthetic data:

| Table | Grain | Rows | Covered cases |
|---|---|---:|---|
| `customers` | One row per customer | 5 | Three segments and `.test` email addresses |
| `orders` | One row per order | 8 | Pending, paid, shipped, and cancelled orders |
| `order_items` | One row per order line | 12 | Single-line and multi-line orders |

UUIDs, timestamps, and values are fixed. Every table and column has a comment so PR-03 can prove
that `tbls` preserves the database documentation. The ClickHouse image is pinned to both an exact
version and a multi-platform digest for reproducible local and CI runs.

Useful database commands:

```bash
make db-up       # Start ClickHouse and wait until it accepts queries
make db-check    # Run the live integration assertions
make db-logs     # Inspect the latest server logs
make db-down     # Stop containers but retain the named volume
make db-reset    # Stop containers and delete the named volume
```

To inspect the data directly:

```bash
docker compose exec clickhouse sh -ec \
  'clickhouse-client --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" \
  --database "$CLICKHOUSE_DB" --query "SHOW TABLES"'
```

Initialization scripts run automatically only when ClickHouse creates an empty data volume.
`002_seed.sql` truncates and reloads the three demo tables, so manually rerunning the two scripts
is deterministic but intentionally destructive inside `commerce_demo`. Never point these scripts
at a real database.

If port `8123` or `9000` is already occupied, copy `.env.example` to `.env` and change
`CLICKHOUSE_HTTP_PORT` or `CLICKHOUSE_NATIVE_PORT`. If startup fails, confirm Docker is running,
use `make db-logs`, then run `make db-reset db-up` after correcting the issue.

## Raw schema documentation with tbls

The `tbls` tool reads ClickHouse table and column comments, adds the two logical relations that
ClickHouse does not enforce, and writes generated-only artifacts to `schema/raw/commerce_demo`.
The tool image is pinned to an exact version and digest; no host installation is required.

```bash
make db-up
make schema-doc schema-lint
make schema-diff
```

Use the complete live contract check before opening a Pull Request:

```bash
make schema-check
```

Expected output includes `README.md`, per-table Markdown with embedded Mermaid ER diagrams, and
`schema.json`. Never edit files under `schema/raw/commerce_demo` manually. Update the database DDL
or `.tbls.yml`, regenerate, inspect the diff, and commit source plus generated changes together.
The generated directory must never contain credentials, a DSN, or database row data.

## CLI

After `make install`:

```bash
.venv/bin/metadata --version
.venv/bin/metadata doctor
```

The wrapper below is also available for lightweight smoke checks:

```bash
./scripts/metadata doctor
```

## GitHub setup

The local repository can be developed and verified without a remote. To publish it while keeping
the existing GitLab remote available:

1. Create an empty GitHub repository with default branch `main`.
2. Do not initialize the GitHub repository with a README, license, or `.gitignore`.
3. Keep GitLab as `gitlab`, add GitHub as `origin`, and push:

```bash
git remote add origin <GITHUB_REMOTE_URL>
git push --set-upstream origin main
git switch --create feat/pr-01-repository-foundation
git push --set-upstream origin feat/pr-01-repository-foundation
```

4. Open a Pull Request targeting `main` and select the default template.

GitHub repository creation and branch-protection settings require repository administration
permissions. They are intentionally not automated by this repository.

## Repository layout

```text
src/metadata_pipeline/     Python package and business logic
tests/                     Unit, contract, integration, and E2E tests
scripts/                   Thin shell wrappers only
.github/workflows/         GitHub Actions workflows
.github/                   Pull Request template
PRD.md                     Product requirements
PR_PLAN.md                 Pull Request delivery plan
```

## Engineering rules

- Business logic belongs in the package, not in shell scripts.
- Domain and application modules do not import GitHub, Docker, database, or LLM SDKs.
- Every behavior change includes tests in the same Pull Request.
- Generated content and credentials are never edited or committed manually.
- Mock/deterministic paths are implemented before live external integrations.
