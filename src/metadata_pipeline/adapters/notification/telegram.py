"""Telegram Bot API adapter with bounded retries and secret-safe errors."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from metadata_pipeline.domain.notification import (
    IndexDoneNotification,
    NotificationEvent,
    PrReviewNotification,
)
from metadata_pipeline.io.notification_settings import NotificationSettings
from metadata_pipeline.ports.notifier import NotificationDeliveryError

TelegramPost = Callable[[str, dict[str, object], float], httpx.Response]


def _default_post(url: str, payload: dict[str, object], timeout: float) -> httpx.Response:
    return httpx.post(url, json=payload, timeout=timeout)


@dataclass(frozen=True)
class TelegramNotifier:
    """Send plain-text messages without logging the credential-bearing endpoint."""

    settings: NotificationSettings
    post: TelegramPost = _default_post
    sleep: Callable[[float], None] = time.sleep

    def send(self, event: NotificationEvent) -> None:
        """Retry transient failures and raise a sanitized error when exhausted."""
        url = f"https://api.telegram.org/bot{self.settings.bot_token}/sendMessage"
        payload: dict[str, object] = {
            "chat_id": self.settings.chat_id,
            "text": render_telegram_message(event),
            "disable_web_page_preview": True,
        }
        if self.settings.message_thread_id is not None:
            payload["message_thread_id"] = self.settings.message_thread_id

        attempts = self.settings.max_retries + 1
        for attempt in range(1, attempts + 1):
            try:
                response = self.post(url, payload, self.settings.timeout_seconds)
                if response.is_success and response.json().get("ok") is True:
                    return
                retryable = response.status_code == 429 or response.status_code >= 500
                reason = f"HTTP {response.status_code}"
                delay = _retry_delay(response, attempt)
            except (httpx.HTTPError, ValueError):
                retryable = True
                reason = "transport or invalid response"
                delay = min(2 ** (attempt - 1), 5)
            if not retryable or attempt == attempts:
                raise NotificationDeliveryError(
                    f"Telegram delivery failed after {attempt} attempt(s): {reason}"
                )
            self.sleep(delay)


def render_telegram_message(event: NotificationEvent) -> str:
    """Render bounded, plain-text messages for all supported event types."""
    commit = event.commit[:12]
    if isinstance(event, PrReviewNotification):
        tables = _bounded_list(event.changed_tables)
        return _fit_message(
            "🔎 Metadata review required\n"
            f"Repository: {event.repository}\n"
            f"PR: #{event.pr_number} ({event.action})\n"
            f"Branch: {event.branch}\n"
            f"Commit: {commit}\n"
            f"Changed tables: {tables}\n"
            f"Review: {event.pr_url}\n"
            f"Run: {event.run_url}"
        )
    if isinstance(event, IndexDoneNotification):
        return _fit_message(
            "✅ Knowledge base updated\n"
            f"Repository: {event.repository}\n"
            f"Collection: {event.collection}\n"
            f"Documents/chunks: {event.document_count}/{event.chunk_count}\n"
            f"Upserted/deleted: {event.upserted_count}/{event.deleted_count}\n"
            f"Unchanged: {event.skipped_count}\n"
            f"Manifest: {event.manifest_hash[:12]}\n"
            f"Commit: {commit}\n"
            f"Run: {event.run_url}"
        )
    jobs = _bounded_list(event.failed_jobs)
    return _fit_message(
        "🚨 Metadata automation failed\n"
        f"Repository: {event.repository}\n"
        f"Workflow: {event.workflow}\n"
        f"Conclusion: {event.conclusion}\n"
        f"Failed jobs: {jobs}\n"
        f"Branch: {event.branch}\n"
        f"Commit: {commit}\n"
        f"Actor/attempt: {event.actor}/{event.attempt}\n"
        f"Run: {event.run_url}"
    )


def _bounded_list(values: tuple[str, ...], *, limit: int = 12) -> str:
    displayed = values[:limit]
    remainder = len(values) - len(displayed)
    suffix = f" (+{remainder} more)" if remainder else ""
    return ", ".join(displayed) + suffix


def _fit_message(message: str, *, limit: int = 4096) -> str:
    if len(message) <= limit:
        return message
    suffix = "\n… message truncated"
    return message[: limit - len(suffix)] + suffix


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    if response.status_code == 429:
        try:
            retry_after = float(response.headers.get("Retry-After", ""))
            if retry_after > 0:
                return min(retry_after, 30)
        except ValueError:
            pass
    return float(min(2 ** (attempt - 1), 5))
