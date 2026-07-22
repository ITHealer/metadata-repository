"""Provider-neutral outbound notification boundary."""

from __future__ import annotations

from typing import Protocol

from metadata_pipeline.domain.notification import NotificationEvent


class NotificationDeliveryError(RuntimeError):
    """Raised when an enabled provider cannot deliver an event."""


class Notifier(Protocol):
    """Deliver one validated notification event."""

    def send(self, event: NotificationEvent) -> None:
        """Send the event or raise a secret-safe delivery error."""
        ...
