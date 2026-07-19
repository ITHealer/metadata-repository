# Reviewer loop: one table from raw schema to approved Markdown

This example updates the business meaning of `orders.total_amount`. Reviewer YAML is the human-owned
source; generated Markdown is never edited directly.

## 1. Prepare a review branch

```bash
git switch main
git pull --ff-only origin main
git switch -c review/orders-total-amount
make install
make review-validate
```

Confirm `schema/raw/commerce_demo/schema.json` already contains `orders.total_amount`. If the raw
schema changed, regenerate it through the schema-sync flow before reviewing business meaning.

## 2. Edit reviewer-owned metadata

Open `metadata/review/commerce_demo/orders.yml` and change only the relevant business fields. For
example:

```yaml
columns:
  total_amount:
    description: Total amount charged for the order after discounts, excluding refunds.
    unit: VND
    caveats:
      - Cancelled orders remain present; exclude them when calculating completed revenue.
```

Do not change `data_type`, raw ClickHouse comments, schema hash, or generated Markdown to force the
desired output. Add evidence and uncertainty explicitly when the statement is not confirmed.

## 3. Validate and preview only this table

```bash
make review-validate
make publish TABLE=orders
```

Inspect:

```bash
git diff -- metadata/review/commerce_demo/orders.yml
git diff -- knowledge/published/commerce_demo/orders.md
```

`make publish TABLE=orders` uses the deterministic renderer and updates only `orders.md`. It does
not delete or regenerate the other table files.

## 4. Optional LLM wording preview

Set the gateway values in the ignored `.env` file. The model name must be one returned by the
gateway `/v1/models` endpoint. For the tested development key, `gpt-oss-120b` supports strict
`json_schema` output.

```dotenv
OPENAI_BASE_URL=https://ai-gateway.urbox.dev/v1
OPENAI_API_KEY=<your-key>
OPENAI_MODEL=gpt-oss-120b
OPENAI_RESPONSE_FORMAT=json_schema
```

Generate an isolated preview:

```bash
make live-uat TABLE=orders
```

Review `build/live/published/commerce_demo/orders.md`. This file is ignored and must not be copied
over the canonical document. If the model suggests better wording, put the accepted meaning back
into `orders.yml`, then rerun validation and deterministic publish. This keeps reviewer intent as
the authoritative source instead of making model prose authoritative.

## 5. Repeat the feedback loop

If the preview is wrong:

1. Edit `orders.yml` again.
2. Run `make review-validate`.
3. Run `make publish TABLE=orders`.
4. Optionally run `make live-uat TABLE=orders`.
5. Inspect both source and generated diffs.

Repeat until the meaning, restrictions, unit, evidence, and safe-use guidance are correct.

## 6. Request human approval

Before setting `document_status: approved`, confirm the Guideline 1 checklist:

- `owner` and `reviewer` are assigned.
- Purpose, grain, appropriate use, and inappropriate use are correct.
- Column meaning, unit/time semantics, allowed values, and caveats are complete.
- Relationship cardinality and row-count risk are confirmed or explicitly uncertain.
- Required evidence has `status: confirmed`; no evidence is `conflicting`.

Then change the status and run the full local gate:

```bash
make review-validate
make publish TABLE=orders
make knowledge-check
make retrieval-smoke
```

## 7. Push the reviewer change

Commit the human-owned input, not a hand-edited Markdown file:

```bash
git add metadata/review/commerce_demo/orders.yml
git commit -m "docs(metadata): review orders total amount"
git push -u origin review/orders-total-amount
```

Open a Pull Request into `main`. With `METADATA_BOT_TOKEN` and `METADATA_BOT_LOGIN` configured, the
`Metadata PR / pr-gate` workflow validates the YAML, regenerates deterministic Markdown, and adds at
most one bot-only commit. Because the renderer is idempotent, changing only `orders.yml` normally
changes only `orders.md`.

Review the bot commit in the Pull Request:

- If incorrect, push another reviewer YAML commit and repeat the loop.
- If correct, approve and merge the Pull Request.
- After merge, the Index Manifest workflow includes the document only when its status is
  `approved`; `needs_review` documents remain excluded.

## 8. Repository setup required for the bot

The repository currently has no Actions secrets or variables. An Owner must configure them in
**GitHub → Repository Settings → Secrets and variables → Actions**:

- Secret `METADATA_BOT_TOKEN`: expiring fine-grained token with repository Contents write access.
- Variable `METADATA_BOT_LOGIN`: login name that owns that token.

The GitHub CLI command `gh` is only an alternative to this web setup. Local `.env` loading and local
review do not require `gh`.
