# Telegram notification runbook

## Scope and safety boundary

The notification core supports three versioned events: `pr_review`, `index_done`, and `job_failed`.
All three delivery paths are connected, but they have independent runtime gates:

- `pr_review` is emitted only after schema sync creates or updates a Draft Pull Request;
- `job_failed` is emitted only for a failed, timed-out, or cancelled allowlisted workflow;
- `index_done` is emitted only after VectorDB apply changes managed points, exact-state verification
  passes, and live retrieval verification passes.

Building the current manifest alone is not a knowledge-base update and never emits `index_done`.

Events are non-secret JSON. Telegram formatting and credentials stay in the provider adapter. The
bot token must never be placed in workflow inputs, command arguments, artifacts, PR content, or
repository files.

## GitHub configuration

Create these Actions secrets:

- `TELEGRAM_BOT_TOKEN`: token issued by BotFather.
- `TELEGRAM_CHAT_ID`: target private chat, group, or channel ID.
- `TELEGRAM_MESSAGE_THREAD_ID`: optional forum-topic ID; omit the secret when unused.

Keep repository variable `TELEGRAM_NOTIFICATIONS_ENABLED=false` while provisioning. Add the bot to
the intended destination, grant only the ability to post, then test in a sandbox chat before
changing the variable to `true`. Telegram enablement is independent of
`SCHEMA_SYNC_ENABLED`.

Provision secrets through GitHub Actions settings or `gh secret set`; never source an untrusted
`.env` file into a shell. The optional thread secret should be absent when the destination does not
use Telegram topics.

Local parsing can be checked without an HTTP request:

```bash
export TELEGRAM_NOTIFICATIONS_ENABLED=false
./scripts/metadata notify --event-file build/notifications/event.json
```

## `pr_review` delivery and deduplication

After schema sync creates or updates its Draft PR, the workflow builds a validated event containing
the PR number and URL, branch, exact pushed commit, changed database/tables, and Actions run URL.
It searches PR comments for this marker:

```text
<!-- metadata-notification:pr_review:<commit-sha> -->
```

An existing marker skips delivery. A new marker is written only after Telegram returns success, so
a failed send remains retryable. A delivery failure leaves the already-pushed schema commit and PR
intact but makes the Actions job visibly fail.

## `index_done` routing

`Apply Vector Index` builds and sends `index_done` only when its apply step reports a changed and
verified state. Live semantic retrieval runs before event construction, so a retrieval regression
fails the workflow without announcing a knowledge-base update. A no-op reconciliation still runs
retrieval health verification but does not send a duplicate update message.

Keep `INDEX_APPLY_ENABLED=false` until gateway and Qdrant credentials, collection bootstrap, initial
apply, idempotent no-op rerun, and changed/removed chunk tests have passed. See
[`vector-index-operations.md`](./vector-index-operations.md) for the rollout gate.

## `job_failed` routing

`Metadata Failure Notification` listens only for completed runs of the explicit metadata workflow
allowlist. It sends an alert for `failure`, `timed_out`, or `cancelled`, and ignores successful or
skipped runs. The listener has only Actions/content read permissions, checks out notification code
from `main`, and never downloads code, cache, or artifacts from the failed run. It reads failed job
names through the Actions API and validates them as event data.

The notifier workflow intentionally does not monitor itself. If Telegram delivery fails, inspect
its failed Actions run and rely on GitHub Actions UI/email until the channel is restored.

## Sandbox UAT sequence

1. Keep the repository variable disabled while validating `.env` parsing and sending clearly
   labelled local `pr_review` and `job_failed` events to the sandbox chat.
2. Provision `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, and the optional topic secret in GitHub.
3. Temporarily enable `TELEGRAM_NOTIFICATIONS_ENABLED` and rerun a known, non-destructive failed
   attempt from an allowlisted workflow.
4. Confirm that `Metadata Failure Notification` collects the failed job name, validates the event,
   and completes Telegram delivery successfully.
5. Trigger a real schema change only after ClickHouse DSNs and allowlists are ready; confirm one
   `pr_review` delivery and its hidden deduplication marker on the active Draft PR.
6. Keep the variable enabled only when the configured destination is the intended operational chat;
   otherwise roll it back to `false` immediately after sandbox evidence is collected.

## Recovery and rotation

- Disable immediately: set `TELEGRAM_NOTIFICATIONS_ENABLED=false`; core workflows continue.
- Telegram outage: use GitHub Actions status and GitHub email notifications as the fallback, then
  rerun the failed notification step/run after service recovery.
- Invalid destination: verify `TELEGRAM_CHAT_ID`, optional topic ID, and bot membership before
  retrying.
- Suspected token exposure: disable the variable, revoke/regenerate the BotFather token, replace the
  GitHub secret, test in the sandbox, then re-enable.
- Duplicate reminder: inspect the PR for the hidden marker matching the commit SHA. Do not add the
  marker manually unless Telegram delivery was independently confirmed.
