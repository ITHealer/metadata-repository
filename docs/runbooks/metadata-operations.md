# Metadata pipeline operations runbook

Use this runbook after the deterministic local checks pass. Never paste a token into a tracked file,
workflow input, issue, Pull Request comment, or build log.

## Clean-machine verification

```bash
git clone git@github.com:ITHealer/metadata-repository.git
cd metadata-repository
make install
make verify
make knowledge-check
make index-build
make retrieval-smoke
```

Use `make db-reset db-up schema-check` when Docker is available and the ClickHouse/tbls integration
must also be reverified.

## Rotate the metadata bot token

1. Create a new expiring, fine-grained token for the dedicated bot identity with only repository
   Contents write permission.
2. Replace the `METADATA_BOT_TOKEN` Actions secret; do not delete the old credential first.
3. Confirm `METADATA_BOT_LOGIN` still matches the token owner.
4. Run a metadata PR and verify exactly one generated commit appears and the latest SHA passes
   `Metadata PR / pr-gate`.
5. Revoke the previous token after the successful test.

Prefer a GitHub App installation token for production because it is short-lived and repository
scoped. See `docs/runbooks/metadata-pr-bot.md` for the PR path and loop-prevention rules.

## Recover failed generation

1. Read the first `PublicationPreflightError` issue code in the Actions log.
2. Fix the reviewer YAML or raw source; never patch `catalog/*/generated/published/**` directly.
3. Run `make review-validate` and `make knowledge-check` locally.
4. Push one human commit. The bot may then replace generated Markdown in one bot-only commit.
5. If a live call failed, switch the PR/workflow back to `GENERATOR_MODE=mock`; live failure must not
   block deterministic publication.

Generation and chunk validation complete before file writes. A failed CI job cannot create a bot
commit because its commit step is downstream of those checks.

## Diagnose a stuck Pull Request check

1. Confirm the PR targets `main` and inspect the latest commit author and changed paths.
2. Confirm the check name is `Metadata PR / pr-gate` rather than an obsolete branch-protection name.
3. For fork PRs, expect validation only: secrets are intentionally unavailable and bot writes are
   skipped.
4. For same-repository PRs, verify `METADATA_BOT_TOKEN` and `METADATA_BOT_LOGIN` exist and the token
   can write the source branch.
5. Re-run the failed job after correcting configuration. Do not add an empty commit to bypass path
   classification.

## Rebuild the index manifest

For a local audit:

```bash
make knowledge-check
make index-build INDEX_BASE=<before-sha> INDEX_HEAD=<after-sha>
make retrieval-smoke
```

Inspect `build/index/manifest.json` and `build/index/actions.json`. Deletions are applied before
upserts, and only chunks with `document_status: approved` and `index_eligible: true` are retained.
For GitHub, re-run the **Index Manifest** workflow on the relevant `main` commit. This MVP uploads an
artifact; a future vector-store adapter must preserve the same delete-before-upsert behavior.

## Upgrade a guideline or prompt version

1. Change the canonical version and its guideline text together.
2. Update the Pydantic contract only if the reviewer input shape changes, then run
   `make review-schema`.
3. Run `make review-draft`; technical/version changes must return affected documents to
   `needs_review` rather than silently preserving approval.
4. Run `make review-validate`, `make knowledge-check`, and `make retrieval-smoke`.
5. Have a domain reviewer inspect the source and generated diffs before approval.
6. Merge through the normal metadata PR. The post-merge workflow rebuilds the complete versioned
   manifest so stale versions are removed.

`OPENAI_PROMPT_VERSION` is independent of the provider model alias. A prompt-only change still
requires regenerated artifacts and UAT evidence because prompt version is stored in document and
chunk provenance.

## Disable live behavior safely

- Keep `ENABLE_LIVE_LLM_UAT=false` or remove the variable.
- Run normal publication with `GENERATOR_MODE=mock`.
- If an unmerged live bot commit exists, revert it on the feature branch and regenerate mock output.
- If live content reached `main`, create a corrective Pull Request; never rewrite `main` history.
