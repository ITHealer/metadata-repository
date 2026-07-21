# Metadata review — no local tools required

This guide is for business and data reviewers. You do not need Python, Docker, ClickHouse, `tbls`,
Make, an API key, or a local clone. GitHub and the metadata bot perform every validation and
generation step.

## Your only editable area

Edit only the requested file:

```text
catalog/<database>/review/<table>.yml
```

Do not edit `generated/raw`, `generated/structured`, or `generated/published`. Those artifacts are
owned by tbls or the metadata bot and CI rejects manual changes.

## Review loop

1. Open the metadata Pull Request in GitHub.
2. Follow the `YAML` link in the `Metadata PR / pr-gate` Actions summary.
3. Choose **Edit this file** and fill only facts you can confirm. Keep
   `document_status: needs_review`.
4. Commit the YAML change to the same PR branch.
5. Wait for `Metadata PR / pr-gate`. The bot validates the YAML, calls the configured LLM when the
   input changed, and commits structured JSON plus a Markdown preview.
6. Follow the `Markdown` link in the Actions summary and read the complete output. Use the displayed
   candidate hash to identify the version you reviewed.
7. If wording is wrong, edit the YAML again and repeat. Never correct generated Markdown directly.
8. When the Markdown is correct, edit only this line in YAML:

   ```yaml
   document_status: approved
   ```

   Do not update every `evidence.status`; `proposed` evidence is allowed. Only resolve an evidence
   item when it is explicitly marked `conflicting`.
9. Commit the status-only change. The bot promotes the exact candidate without calling the LLM
   again. If business content changed in the same commit, CI blocks the approval.
10. Confirm the candidate state is `promoted`, checks are green, then approve the Pull Request.

## What to provide

Use [Guideline 1](../../guidelines/reviewer_metadata_guideline.md) for field-level examples. At a
minimum, confirm the table grain and purpose, appropriate/inappropriate uses, column meanings,
sensitivity, relationship risks, evidence, freshness, and caveats relevant to the table. Add the
owner and reviewer when known; leaving their generated value as `unassigned` does not block
approval. Leave uncertainty explicit; do not guess.

## How to respond to failures

- `unknown_table` or `unknown_column`: remove or correct the identifier; it does not exist in raw
  ClickHouse schema.
- `stale_candidate`: the YAML, raw schema, contract, guideline, model, or prompt changed. Keep
  `needs_review` and wait for a new candidate.
- `approval_without_reviewed_candidate`: revert status to `needs_review`, let the bot generate a new
  candidate, review it, then make a separate status-only approval commit.
- Gateway or bot failure: do not run anything locally. Ask the developer/platform owner to re-run or
  repair CI.
