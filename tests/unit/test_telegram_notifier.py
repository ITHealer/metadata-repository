"""Tests for Telegram formatting, delivery, retries, and sanitized errors."""

from __future__ import annotations

import httpx
import pytest

from metadata_pipeline.adapters.notification.telegram import (
    TelegramNotifier,
    render_telegram_message,
)
from metadata_pipeline.domain.notification import (
    IndexDoneNotification,
    JobFailedNotification,
    PrReviewNotification,
)
from metadata_pipeline.io.notification_settings import NotificationSettings
from metadata_pipeline.ports.notifier import NotificationDeliveryError


def _settings(*, retries: int = 0) -> NotificationSettings:
    return NotificationSettings(
        enabled=True,
        bot_token="secret-token",
        chat_id="-100123",
        message_thread_id=9,
        timeout_seconds=3.0,
        max_retries=retries,
    )


def _pr_event() -> PrReviewNotification:
    return PrReviewNotification(
        event_id="pr_review:" + "a" * 40,
        repository="acme/metadata",
        branch="automation/schema-sync-1",
        commit="a" * 40,
        workflow="Scheduled Schema Sync",
        run_url="https://github.example/runs/1",
        action="updated",
        pr_number=12,
        pr_url="https://github.example/pr/12",
        changed_tables=("commerce_demo.orders",),
    )


def test_telegram_sends_plain_text_to_expected_chat_and_thread() -> None:
    calls: list[tuple[str, dict[str, object], float]] = []

    def post(url: str, payload: dict[str, object], timeout: float) -> httpx.Response:
        calls.append((url, payload, timeout))
        return httpx.Response(200, json={"ok": True})

    TelegramNotifier(_settings(), post=post).send(_pr_event())

    url, payload, timeout = calls[0]
    assert url.endswith("/botsecret-token/sendMessage")
    assert payload["chat_id"] == "-100123"
    assert payload["message_thread_id"] == 9
    assert "#12 (updated)" in str(payload["text"])
    assert "commerce_demo.orders" in str(payload["text"])
    assert timeout == 3.0


def test_telegram_retries_transient_status_and_sanitizes_final_error() -> None:
    statuses = iter((429, 500))
    sleeps: list[float] = []

    def post(_: str, __: dict[str, object], ___: float) -> httpx.Response:
        status = next(statuses)
        headers = {"Retry-After": "7"} if status == 429 else {}
        return httpx.Response(status, headers=headers, json={"ok": False})

    with pytest.raises(NotificationDeliveryError) as error:
        TelegramNotifier(_settings(retries=1), post=post, sleep=sleeps.append).send(_pr_event())

    assert sleeps == [7]
    assert "HTTP 500" in str(error.value)
    assert "secret-token" not in str(error.value)


def test_telegram_does_not_retry_permanent_client_error() -> None:
    calls = 0

    def post(_: str, __: dict[str, object], ___: float) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401, json={"ok": False})

    with pytest.raises(NotificationDeliveryError, match="HTTP 401"):
        TelegramNotifier(_settings(retries=3), post=post).send(_pr_event())

    assert calls == 1


def test_all_event_templates_include_operator_context() -> None:
    index_event = IndexDoneNotification(
        event_id="index_done:" + "b" * 40,
        repository="acme/metadata",
        branch="main",
        commit="b" * 40,
        workflow="Apply Index",
        run_url="https://github.example/runs/2",
        collection="metadata-v1",
        manifest_hash="c" * 64,
        document_count=3,
        chunk_count=20,
        upserted_count=4,
        deleted_count=1,
    )
    failed_event = JobFailedNotification(
        event_id="job_failed:3:1",
        repository="acme/metadata",
        branch="main",
        commit="d" * 40,
        workflow="Quality",
        run_url="https://github.example/runs/3",
        conclusion="failure",
        actor="octocat",
        attempt=1,
        failed_jobs=("lint", "test"),
    )

    assert "Knowledge base updated" in render_telegram_message(index_event)
    assert "metadata-v1" in render_telegram_message(index_event)
    assert "Metadata automation failed" in render_telegram_message(failed_event)
    assert "lint, test" in render_telegram_message(failed_event)
