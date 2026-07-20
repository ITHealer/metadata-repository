# Metadata Pull Request bot runbook

Generated Markdown normally belongs to the bot. The only human-commit exception is a deterministic
generation-contract migration that changes an allowlisted generator/domain/renderer source file in
the same PR. That path runs `validate-migration`: committed Markdown must be byte-identical to fresh
generation. Merely changing reviewer input alongside Markdown remains rejected.

## Purpose

The `Metadata PR / pr-gate` workflow implements this loop:

```text
human changes an authoritative metadata input
  -> deterministic validation and publication
  -> bot commits only catalog/*/generated/published/**
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

A GitHub App installation token is the preferred production replacement because it is short-lived.
When adopting it, mint the token inside the job and pass it to checkout/push; retain the same
allowlist and loop guard.

After the workflow has passed a real test PR, configure branch protection for `main` to require the
stable check name `Metadata PR / pr-gate` and require branches to be up to date before merge.

## Expected path behavior

| Latest commit | Result |
|---|---|
| No metadata path | Successful no-op gate |
| Raw/reviewer/guideline/config input | Validate, generate, validate, chunk, then bot commit if needed |
| Bot-owned `catalog/*/generated/published/**` only | Validate only; no second generation or commit |
| Human or mixed commit containing published output | Fail with `bot-owned generated output` |
| Fork requiring a generated diff | Validate without secrets, then fail before push with an actionable message |

Renames check both the old and new path, so moving a protected published file cannot bypass the
guard.

## Recovery

- Missing token: set or rotate `METADATA_BOT_TOKEN`, then re-run the failed job.
- Wrong bot identity: update `METADATA_BOT_LOGIN` to the account that owns the token.
- Stale generated output: remove human edits under `catalog/*/generated/published/**`, update the authoritative
  input, and push a new commit. The bot will regenerate the output.
- Bot push rejected: confirm token expiry, Contents permission, machine-user repository access, and
  branch rules that permit the bot to push to the PR branch.
- Repeated bot commits: disable the workflow temporarily, verify that the bot commit contains only
  `catalog/*/generated/published/**`, and run `make knowledge-check` twice locally. The second run must be
  unchanged before re-enabling the workflow.

Do not solve a stuck run by switching to `pull_request_target` or by sending secrets to forked Pull
Requests.
