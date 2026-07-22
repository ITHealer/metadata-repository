"""Tests for notification contracts, settings, and provider-neutral delivery."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from metadata_pipeline.application.send_notification import (
    NotificationOutcome,
    send_notification,
)
from metadata_pipeline.domain.notification import (
    JobFailedNotification,
    PrReviewNotification,
)
from metadata_pipeline.io.notification_json import (
    NotificationEventError,
    load_notification_event,
    write_notification_event,
)
from metadata_pipeline.io.notification_settings import (
    NotificationConfigurationError,
    NotificationSettings,
)


def _pr_event() -> PrReviewNotification:
    return PrReviewNotification(
        event_id="pr_review:" + "a" * 40,
        repository="acme/metadata",
        branch="automation/schema-sync-1",
        commit="a" * 40,
        workflow="Scheduled Schema Sync",
        run_url="https://github.example/runs/1",
        action="created",
        pr_number=12,
        pr_url="https://github.example/pr/12",
        changed_tables=("commerce_demo.orders",),
    )


def test_notification_json_round_trip_and_rejects_unknown_event(tmp_path: Path) -> None:
    path = tmp_path / "event.json"
    event = _pr_event()

    assert write_notification_event(path, event)
    assert load_notification_event(path) == event

    path.write_text('{"event_type":"unknown"}', encoding="utf-8")
    with pytest.raises(NotificationEventError, match="unsupported event_type"):
        load_notification_event(path)


def test_notification_models_require_deterministic_collections() -> None:
    with pytest.raises(ValidationError, match="changed_tables must be sorted and unique"):
        _pr_event().model_copy(
            update={"changed_tables": ("commerce_demo.orders", "commerce_demo.orders")}
        ).model_validate(
            _pr_event().model_dump()
            | {"changed_tables": ("commerce_demo.orders", "commerce_demo.orders")}
        )

    with pytest.raises(ValidationError, match="failed_jobs must be sorted and unique"):
        JobFailedNotification(
            event_id="job_failed:1",
            repository="acme/metadata",
            branch="main",
            commit="b" * 40,
            workflow="Quality",
            run_url="https://github.example/runs/2",
            conclusion="failure",
            actor="octocat",
            attempt=1,
            failed_jobs=("lint", "lint"),
        )


def test_disabled_settings_need_no_secrets_and_skip_adapter() -> None:
    settings = NotificationSettings.from_env({"TELEGRAM_NOTIFICATIONS_ENABLED": "false"})

    assert send_notification(_pr_event(), settings, None) is NotificationOutcome.DISABLED


def test_enabled_settings_require_credentials_without_exposing_token() -> None:
    with pytest.raises(NotificationConfigurationError, match="TELEGRAM_BOT_TOKEN"):
        NotificationSettings.from_env({"TELEGRAM_NOTIFICATIONS_ENABLED": "true"})

    settings = NotificationSettings.from_env(
        {
            "TELEGRAM_NOTIFICATIONS_ENABLED": "true",
            "TELEGRAM_BOT_TOKEN": "very-secret-token",
            "TELEGRAM_CHAT_ID": "-100123",
            "TELEGRAM_MESSAGE_THREAD_ID": "7",
        }
    )

    assert settings.message_thread_id == 7
    assert "very-secret-token" not in repr(settings)


def test_notification_json_never_contains_provider_credentials(tmp_path: Path) -> None:
    path = tmp_path / "event.json"
    write_notification_event(path, _pr_event())

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert "token" not in json.dumps(payload).lower()
    assert "chat_id" not in payload
