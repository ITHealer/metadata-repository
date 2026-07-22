# Telegram notification runbook

## Scope and safety boundary

The notification core supports three versioned events: `pr_review`, `index_done`, and `job_failed`.
`pr_review` and centralized `job_failed` delivery are connected. `index_done` must remain
unconnected until a
later workflow has both applied the VectorDB update and passed retrieval verification; building the
current manifest alone is not a knowledge-base update.

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

## `job_failed` routing

`Metadata Failure Notification` listens only for completed runs of the explicit metadata workflow
allowlist. It sends an alert for `failure`, `timed_out`, or `cancelled`, and ignores successful or
skipped runs. The listener has only Actions/content read permissions, checks out notification code
from `main`, and never downloads code, cache, or artifacts from the failed run. It reads failed job
names through the Actions API and validates them as event data.

The notifier workflow intentionally does not monitor itself. If Telegram delivery fails, inspect
its failed Actions run and rely on GitHub Actions UI/email until the channel is restored.

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
