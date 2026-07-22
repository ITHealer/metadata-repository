"""Strict JSON persistence for notification events."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from metadata_pipeline.domain.notification import (
    IndexDoneNotification,
    JobFailedNotification,
    NotificationEvent,
    PrReviewNotification,
)
from metadata_pipeline.io.atomic_text import write_text_if_changed


class NotificationEventError(ValueError):
    """Raised when a notification event is missing or violates its contract."""


def load_notification_event(path: Path) -> NotificationEvent:
    """Load the concrete event type selected by the validated discriminator."""
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise NotificationEventError("event payload must be a JSON object")
        event_type = payload.get("event_type")
        if event_type == "pr_review":
            return PrReviewNotification.model_validate(payload)
        if event_type == "index_done":
            return IndexDoneNotification.model_validate(payload)
        if event_type == "job_failed":
            return JobFailedNotification.model_validate(payload)
        raise NotificationEventError(f"unsupported event_type: {event_type!r}")
    except NotificationEventError:
        raise
    except (FileNotFoundError, OSError, json.JSONDecodeError, ValidationError) as error:
        raise NotificationEventError(
            f"unable to load notification event {path}: {error}"
        ) from error


def write_notification_event(path: Path, event: NotificationEvent) -> bool:
    """Write a deterministic event without provider credentials."""
    content = json.dumps(
        event.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    return write_text_if_changed(path, content + "\n")
