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

From a clean checkout:

```bash
git clone git@github.com:ITHealer/metadata-repository.git
cd metadata-repository
make install
make verify
make knowledge-check
make index-build
make retrieval-smoke
```

The first two commands install an isolated Python environment and run the offline quality gates.
The remaining commands prove that published Markdown, semantic chunks, the approved-only index
manifest, and the ten golden retrieval questions still satisfy the same contracts. Docker is needed
only for the live ClickHouse/tbls integration path described below.

Useful commands:

```bash
make help       # List supported commands
make format     # Apply Ruff fixes and formatting
make lint       # Check lint and formatting
make typecheck  # Run strict mypy checks
make test       # Run unit tests
make coverage   # Enforce coverage for domain/application/validation core
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

## Database profiles and catalog scope

Every database is selected by a lowercase repository key such as `commerce_demo`, `urgift`, or
`urcard`. Its profile under `config/databases/<database>/database.yml` maps that key to the exact
ClickHouse database name and explicitly allowlists the tables this repository may document.

```bash
make catalog-check DATABASE=commerce_demo
make review-validate DATABASE=commerce_demo
make publish DATABASE=commerce_demo
make catalog-check-all
```

The CLI derives raw, review, structured, published, and chunk paths from `--database`; callers do
not need to assemble paths manually. `catalog-check` fails if tbls returned an unexpected table,
an allowlisted table is missing, or the raw database name differs from the profile. Production
profiles should use the exact table list supplied by the data owner rather than a wildcard.

## Raw schema documentation with tbls

The `tbls` tool reads ClickHouse table and column comments, adds the two logical relations that
ClickHouse does not enforce, and writes generated-only artifacts to `catalog/commerce_demo/generated/raw`.
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
`schema.json`. Never edit files under `catalog/commerce_demo/generated/raw` manually. Update the database DDL
or `config/databases/commerce_demo/tbls.yml`, regenerate, inspect the diff, and commit source plus generated changes together.
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

## Reviewer metadata contract

Reviewer-owned metadata is stored as YAML under `catalog/commerce_demo/review`. Its shape is
defined once in the Pydantic models and exported to `contracts/reviewer_metadata.schema.json` for
editor/tooling support. The validator also performs checks JSON Schema cannot express by itself:
every declared table, column, and relationship endpoint must exist in the raw tbls `schema.json`.

```bash
make review-schema    # Regenerate JSON Schema from Pydantic
make review-draft     # Create/refresh drafts without overwriting human metadata
make review-validate  # Validate the three reviewer files against raw schema.json
make review-check     # Run both; this is the GitHub Actions gate
```

`make review-draft` is deterministic: unchanged schema produces no file rewrite. A new column is
added as a `proposed` draft, while existing purpose, grain, ownership, rules, and evidence are
preserved. Technical changes update `schema_hash` and return the document to `needs_review`.
Removed tables or columns require explicit reviewer cleanup and are never deleted silently.

Read [Guideline 1](./guidelines/reviewer_metadata_guideline.md) before changing reviewer content.
[Guideline 2](./guidelines/llm_transformation_guideline.md) defines how a later publish step must
merge validated review metadata with raw ClickHouse facts for chunking and retrieval.
`make schema-doc` only regenerates raw technical documentation; it does not merge reviewer metadata
or produce enriched output.

## Publish metadata and build semantic chunks

PR-06 defines provider-neutral `PublishedDocument` and `Chunk` contracts plus a
`DocumentGenerator` port. The publish use case validates the entire raw/reviewer batch before it
writes anything, then renders generated-only Markdown and builds chunks directly from the
structured model. It never parses the Markdown back into business data.

Run the deterministic, network-free path with:

```bash
make publish             # raw schema + reviewer YAML -> committed Markdown previews
make published-validate  # fail when committed Markdown was edited or is stale
make chunk-dry-run       # structured documents -> build/chunks/commerce_demo.jsonl
make knowledge-check     # run all three steps in order
```

`SOURCE_REVIEW_COMMIT` defaults to the latest Git commit that changed the review directory. CI uses
the same value. For a reproducibility check or a non-Git environment, pass it explicitly:

```bash
make knowledge-check SOURCE_REVIEW_COMMIT=<40-character-commit-sha>
```

Files under `catalog/commerce_demo/generated/published` are generated and committed so reviewers can see
the exact output diff. Do not edit them manually. Change reviewer YAML, run `make knowledge-check`,
inspect both input and output, then commit them together. The JSONL file under `build/chunks` is a
local/CI artifact and is intentionally ignored by Git.

Documents still marked `needs_review` are published as preview files with
`index_eligible: false`. A document can become index-eligible only after its reviewer contract is
valid and its status is `approved`; PR-06 does not write to an index.

Generated review candidates have a separate machine-readable source under
`catalog/<database>/generated/structured/<table>.json`. Each candidate stores hashes for the raw
schema, reviewer content excluding `document_status`, contract, transformation guideline, model,
and prompt. A status-only change from `needs_review` to `approved` therefore keeps the same input
fingerprint. Any simultaneous business-content change makes the candidate stale and blocks
promotion with `approval_without_reviewed_candidate`.

Promotion has no `DocumentGenerator` dependency and cannot call the LLM. It changes only approval
metadata (`document_status`, `index_eligible`, and source commit); the Markdown body beginning at
`## Summary` must retain the exact hash the reviewer saw. This turns approval into an auditable
state transition instead of a second non-deterministic generation request.

`DeterministicDocumentGenerator` is the factual baseline.
`OpenAICompatibleDocumentGenerator` calls an OpenAI-compatible LiteLLM gateway. A `needs_review`
document permits only a summary rewrite. An `approved` document permits structured narrative
rewrites for purpose/use guidance, descriptions, relationships, and business rules. Identifiers,
types, nullability, units, joins, cardinality, evidence, ownership, versions, and review status stay
locked to the deterministic baseline. Every live result passes the same published-document and
chunk validators. A generation or validation failure happens during preflight, before any published
file or chunk artifact is changed.

The default model name is a gateway alias, not a provider-specific Bedrock identifier. Platform
owners can remap the alias or developers can select another gateway model without changing code:

```bash
export OPENAI_BASE_URL=https://ai-gateway.dev/v1
export OPENAI_API_KEY=<gateway-key>
export OPENAI_MODEL=gpt-5.4-nano
export OPENAI_RESPONSE_FORMAT=json_schema  # or json_object for a less capable model
```

Never commit the key. `.env.example` documents the supported variables, while `.env` is ignored.
No live gateway request is part of the default test suite; mocked HTTP tests verify the endpoint,
model routing, response format, structured parsing, and failure behavior without network access.

## Manual live LLM UAT

Live output is deliberately isolated under `build/live`; it never overwrites committed previews:

```bash
cp .env.example .env
# Edit .env and set OPENAI_API_KEY; do not commit this file.
make live-uat
```

Local commands automatically read the nearest `.env`. Values already exported by the shell take
precedence, which lets CI inject secrets without being overridden by a file. The `gh` command is the
GitHub CLI and is needed only to configure or trigger GitHub Actions; it is not required for local
`make live-uat`.

During one-table review, avoid unnecessary model calls and preserve every other generated file:

```bash
make publish TABLE=orders               # deterministic canonical Markdown
make live-uat TABLE=orders              # isolated LLM preview and chunks
```

`TABLE` must match a reviewer YAML table name. A selective publish never prunes other Markdown;
the unfiltered full-batch command remains responsible for orphan cleanup.

The same operation is available through the manual **Live LLM UAT** GitHub Actions workflow. Set
repository variable `ENABLE_LIVE_LLM_UAT=true`, repository secret `OPENAI_API_KEY`, and optionally
repository variable `OPENAI_BASE_URL`, then dispatch the workflow with the desired gateway alias.
The job uploads the live Markdown, chunks, and retrieval report for 14 days. It has read-only
repository permissions and does not commit or publish an index.

The committed demo reviews intentionally remain `needs_review`; a maintainer must not promote them
only to exercise a model. Full approved-narrative behavior is covered offline by a structured mock
gateway contract test. Run a real approved live UAT only after the domain reviewer confirms the
review YAML and changes `document_status` through the normal Pull Request flow.

See the [MVP UAT record](./docs/uat/metadata-mvp.md) and
[operations runbook](./docs/runbooks/metadata-operations.md) for evidence, setup, failure recovery,
token rotation, re-indexing, and guideline upgrades.
The [one-table reviewer loop](./docs/runbooks/reviewer-loop.md) gives a command-by-command example
from editing reviewer YAML through bot regeneration, approval, merge, and approved-only indexing.

## Metadata Pull Request automation

After PR-07 is merged, every Pull Request into `main` receives the stable
`Metadata PR / pr-gate` check. A normal metadata change follows this sequence:

```text
reviewer input commit
  -> review validation
  -> deterministic publish + chunk validation
  -> bot-only generated Markdown commit
  -> validation-only run on the latest bot SHA
```

The workflow classifies the full PR diff and the latest commit separately. This prevents a bot
commit from starting another generation while still rejecting a human or mixed commit that changes
`catalog/*/generated/published/**`. Unrelated PRs complete as a successful no-op instead of leaving a required
check pending.

The MVP requires repository secret `METADATA_BOT_TOKEN` and repository variable
`METADATA_BOT_LOGIN`. Use a dedicated, expiring, fine-grained machine-user token with repository
Contents write permission. A GitHub App installation token is the preferred production upgrade.
GitHub's default token is not used for the bot loop because workflow-created events normally do not
start another unrestricted workflow run. Fork PRs receive no bot secret and cannot push generated
output.

See [the metadata bot runbook](./docs/runbooks/metadata-pr-bot.md) for setup, path behavior,
branch-protection rollout, and recovery steps.

## Automated schema synchronization

The `Schema Sync` workflow is manual-first and uses only the disposable ClickHouse fixture in this
MVP. A baseline run exits without creating an empty PR. The `additive_test` UAT scenario adds
`orders.channel` and `order_events`, regenerates tbls output, refreshes reviewer drafts, and opens a
Draft PR containing a table-level impact summary.

```text
workflow_dispatch / gated schedule
  -> disposable ClickHouse
  -> tbls doc + lint
  -> deterministic reviewer draft refresh
  -> source diff allowlist
  -> timestamped branch + Draft PR
```

The workflow can commit only `catalog/*/generated/raw/**` and `catalog/*/review/**`; it never pushes directly to
`main`. Set `ENABLE_SCHEMA_SYNC=true` only after baseline and additive manual UAT pass. Publishing
from a changed run also needs `METADATA_BOT_TOKEN`. See the
[schema sync runbook](./docs/runbooks/schema-sync.md) for rollout and review steps.

## Index manifest and retrieval smoke test

PR-09 adds a post-merge `Index Manifest` workflow. It rebuilds a complete, versioned manifest from
structured chunks whenever `catalog/*/generated/published/**` changes on `main`, maps Git add/modify/delete/
rename changes into audit actions, and uploads the manifest plus retrieval report as artifacts.

```bash
make index-build      # writes build/index/manifest.json and actions.json
make retrieval-smoke # evaluates 10 golden questions and required facts
```

Only `approved` chunks enter the manifest. The three committed demo reviews remain `needs_review`,
so the real demo manifest is currently empty by design. Retrieval CI uses the same metadata with an
in-memory approved test status; it never modifies reviewer-owned YAML. The deterministic lexical
smoke test requires at least 90% top-3 document accuracy and all required facts in the retrieved
chunks.

See [the index manifest runbook](./docs/runbooks/index-manifest.md) for lifecycle, version
replacement, report interpretation, and recovery.

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
