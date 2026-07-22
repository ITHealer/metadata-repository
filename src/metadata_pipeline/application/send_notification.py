"""Provider-neutral notification delivery use case."""

from __future__ import annotations

from enum import Enum

from metadata_pipeline.domain.notification import NotificationEvent
from metadata_pipeline.io.notification_settings import NotificationSettings
from metadata_pipeline.ports.notifier import Notifier


class NotificationOutcome(str, Enum):
    """Operator-visible result without treating a disabled channel as a failure."""

    SENT = "sent"
    DISABLED = "disabled"


def send_notification(
    event: NotificationEvent,
    settings: NotificationSettings,
    notifier: Notifier | None,
) -> NotificationOutcome:
    """Skip cleanly when disabled; otherwise require and call the adapter."""
    if not settings.enabled:
        return NotificationOutcome.DISABLED
    if notifier is None:
        raise ValueError("an enabled notification requires a notifier")
    notifier.send(event)
    return NotificationOutcome.SENT
