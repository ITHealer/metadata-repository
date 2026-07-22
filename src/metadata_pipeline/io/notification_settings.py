"""Runtime settings for outbound operator notifications."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from metadata_pipeline.io.runtime_environment import load_runtime_environment


class NotificationConfigurationError(ValueError):
    """Raised before delivery when notification settings are invalid."""


@dataclass(frozen=True)
class NotificationSettings:
    """Validated Telegram settings with secret-safe representation."""

    enabled: bool
    bot_token: str = field(default="", repr=False)
    chat_id: str = field(default="", repr=False)
    message_thread_id: int | None = None
    timeout_seconds: float = 5.0
    max_retries: int = 2

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> NotificationSettings:
        """Load settings while allowing a disabled configuration to omit secrets."""
        values = load_runtime_environment(environ)
        enabled = _boolean(values, "TELEGRAM_NOTIFICATIONS_ENABLED", default=False)
        token = values.get("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = values.get("TELEGRAM_CHAT_ID", "").strip()
        if enabled and not token:
            raise NotificationConfigurationError(
                "TELEGRAM_BOT_TOKEN is required when Telegram notifications are enabled"
            )
        if enabled and not chat_id:
            raise NotificationConfigurationError(
                "TELEGRAM_CHAT_ID is required when Telegram notifications are enabled"
            )
        thread_id = _optional_int(values, "TELEGRAM_MESSAGE_THREAD_ID")
        timeout = _positive_float(values, "TELEGRAM_TIMEOUT_SECONDS", 5.0)
        retries = _non_negative_int(values, "TELEGRAM_MAX_RETRIES", 2)
        return cls(enabled, token, chat_id, thread_id, timeout, retries)


def _boolean(values: Mapping[str, str], name: str, *, default: bool) -> bool:
    raw = values.get(name, "").strip().lower()
    if not raw:
        return default
    if raw == "true":
        return True
    if raw == "false":
        return False
    raise NotificationConfigurationError(f"{name} must be 'true' or 'false'")


def _optional_int(values: Mapping[str, str], name: str) -> int | None:
    raw = values.get(name, "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError as error:
        raise NotificationConfigurationError(f"{name} must be an integer") from error
    if value <= 0:
        raise NotificationConfigurationError(f"{name} must be greater than zero")
    return value


def _positive_float(values: Mapping[str, str], name: str, default: float) -> float:
    raw = values.get(name, "").strip()
    try:
        value = float(raw) if raw else default
    except ValueError as error:
        raise NotificationConfigurationError(f"{name} must be a number") from error
    if value <= 0:
        raise NotificationConfigurationError(f"{name} must be greater than zero")
    return value


def _non_negative_int(values: Mapping[str, str], name: str, default: int) -> int:
    raw = values.get(name, "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError as error:
        raise NotificationConfigurationError(f"{name} must be an integer") from error
    if value < 0:
        raise NotificationConfigurationError(f"{name} must not be negative")
    return value
