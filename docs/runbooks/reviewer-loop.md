# Reviewer loop: one table from YAML to approved Markdown

This example updates the business meaning of `orders.total_amount`. Reviewer YAML is the
human-owned source; generated JSON and Markdown are bot-owned outputs.

## 1. Developer prepares the onboarding Pull Request

The developer extracts the allowlisted ClickHouse schema and creates deterministic YAML templates
while the database profile is still disabled:

```bash
make schema-check DATABASE=commerce_demo
make review-draft DATABASE=commerce_demo
make review-validate DATABASE=commerce_demo
```

After inspecting the raw output, the developer changes
`config/databases/commerce_demo/database.yml` to `enabled: true`, commits the profile, raw schema,
and reviewer templates, then opens a Draft Pull Request. This activation commit opts the database
into the Metadata PR workflow.

## 2. Reviewer edits only YAML in GitHub

The reviewer opens `catalog/commerce_demo/review/orders.yml` in the PR and changes only confirmed
business fields. Keep `document_status: needs_review`:

```yaml
columns:
  total_amount:
    description: Total amount charged for the order after discounts, excluding refunds.
    unit: VND
    caveats:
      - Cancelled orders remain present; exclude them when calculating completed revenue.
```

Commit the edit to the same PR branch through GitHub. The reviewer does not clone the repository,
run Make, configure an API key, or edit generated files.

## 3. CI validates and the bot generates

`Metadata PR / pr-gate` validates the table and column names against raw `schema.json`. For a valid
input change, the configured gateway generates a structured candidate and Markdown preview. The bot
commits only:

```text
catalog/commerce_demo/generated/structured/orders.json
catalog/commerce_demo/generated/published/orders.md
```

The workflow runs again on the bot commit in validation-only mode, preventing a generation loop.

## 4. Reviewer checks the Markdown

Open `catalog/commerce_demo/generated/published/orders.md` from the PR diff or Actions summary.

- If it is incorrect, edit `orders.yml` again, keep `needs_review`, and commit. CI generates a new
  candidate.
- If it is correct, continue to the approval step. Never fix wording directly in Markdown.

## 5. Reviewer approves the exact candidate

Change only:

```yaml
document_status: approved
```

Commit that status-only edit. The bot verifies the candidate fingerprint and promotes the exact
Markdown already reviewed without calling the LLM again. A commit that changes both business
content and status is rejected; first regenerate under `needs_review`, then approve separately.

## 6. Merge and index

When `Quality` and `Metadata PR / pr-gate` are green and the candidate state is `promoted`, approve
and merge the Pull Request. The Index Manifest workflow runs after merge because approved structured
and published artifacts changed. Documents still in `needs_review` remain excluded from indexing.

## Required GitHub configuration

An Owner configures these under **Settings → Secrets and variables → Actions**:

- Secret `METADATA_BOT_TOKEN`: fine-grained token with repository Contents write access.
- Secret `OPENAI_API_KEY`: gateway credential.
- Variable `METADATA_BOT_LOGIN`: account that owns the bot token.
- Variables `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_RESPONSE_FORMAT`, and
  `OPENAI_PROMPT_VERSION`.
- Variable `METADATA_GENERATOR_MODE=live` when real LLM generation is required.

The local `.env` is only for developer-run UAT and is never used as a substitute for GitHub Actions
secrets.
