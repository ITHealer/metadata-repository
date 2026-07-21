# Metadata Pull Request bot runbook

Generated candidate JSON and Markdown belong to the bot. Reviewer commits contain only YAML input.

## Purpose

The `Metadata PR / pr-gate` workflow implements this loop:

```text
human changes reviewer YAML
  -> deterministic validation
  -> LLM generates only missing or stale needs_review candidates
  -> status-only approval promotes the reviewed candidate without LLM access
  -> bot commits only catalog/*/generated/{structured,published}/**
  -> latest bot SHA runs validation only
  -> required check passes on the latest SHA
```

It never uses `pull_request_target` and never gives fork code a write token or repository secret.

## Repository configuration

For the MVP, create a dedicated fine-grained personal access token owned by a machine user:

1. Limit repository access to this repository.
2. Grant repository Contents read/write; do not grant administration access.
3. Set a short expiry and record the rotation owner.
4. Store it as the Actions secret `METADATA_BOT_TOKEN`.
5. Set the Actions repository variable `METADATA_BOT_LOGIN` to the token owner's exact GitHub login.

Configure the gateway separately:

- Secret `OPENAI_API_KEY`.
- Variables `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_RESPONSE_FORMAT`, and
  `OPENAI_PROMPT_VERSION`.
- Variable `METADATA_GENERATOR_MODE=live` for production candidate generation.

`OPENAI_PROMPT_VERSION` is part of the candidate fingerprint. Increment it whenever prompt behavior
changes; `workflow-neutral-narrative-v2` keeps review, approval, preview, and indexing state out of
LLM narrative so a status-only promotion cannot make the reviewed body stale.

Do not store the API key in an Actions variable or repository file. The workflow has no fallback
from `live` to `mock`; missing gateway configuration fails visibly. An approval-only sync does not
load gateway settings or create an LLM client.

A GitHub App installation token is the preferred production replacement because it is short-lived.
When adopting it, mint the token inside the job and pass it to checkout/push; retain the same
allowlist and loop guard.

After the workflow has passed a real test PR, configure branch protection for `main` to require the
stable check name `Metadata PR / pr-gate` and require branches to be up to date before merge.

## Expected path behavior

| Latest commit | Result |
|---|---|
| No metadata path | Successful no-op gate |
| Raw/reviewer/guideline/config input | Validate, sync candidates, then bot commit if needed |
| Bot-owned structured/Markdown output only | Validate only; no second generation or commit |
| Human or mixed commit containing published output | Fail with `bot-owned generated output` |
| Fork requiring a generated diff | Validate without secrets, then fail before push with an actionable message |

Renames check both the old and new path, so moving a protected published file cannot bypass the
guard.

## Recovery

- Missing token: set or rotate `METADATA_BOT_TOKEN`, then re-run the failed job.
- Wrong bot identity: update `METADATA_BOT_LOGIN` to the account that owns the token.
- Stale generated output: remove human edits under `catalog/*/generated/{structured,published}/**`, update the authoritative
  input, and push a new commit. The bot will regenerate the output.
- Bot push rejected: confirm token expiry, Contents permission, machine-user repository access, and
  branch rules that permit the bot to push to the PR branch.
- Repeated bot commits: disable the workflow temporarily, verify that the bot commit contains only
  `catalog/*/generated/{structured,published}/**`, and run `make candidate-sync` twice locally. The second run must be
  unchanged before re-enabling the workflow.

Do not solve a stuck run by switching to `pull_request_target` or by sending secrets to forked Pull
Requests.
