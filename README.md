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
- Docker with Compose will be required starting from PR-02.

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
