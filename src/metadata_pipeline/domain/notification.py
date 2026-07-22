"""Versioned, non-secret notification event contracts."""

from __future__ import annotations

from typing import Literal, Union

from pydantic import Field, model_validator

from metadata_pipeline.domain.review import StrictModel


class NotificationBase(StrictModel):
    """Fields shared by every operator notification."""

    event_version: Literal["notification-event-v1"] = "notification-event-v1"
    event_id: str = Field(min_length=1)
    repository: str = Field(pattern=r"^[^/\s]+/[^/\s]+$")
    branch: str = Field(min_length=1)
    commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    workflow: str = Field(min_length=1)
    run_url: str = Field(pattern=r"^https?://\S+$")


class PrReviewNotification(NotificationBase):
    """A schema-sync Pull Request requires human review."""

    event_type: Literal["pr_review"] = "pr_review"
    action: Literal["created", "updated"]
    pr_number: int = Field(gt=0)
    pr_url: str = Field(pattern=r"^https?://\S+$")
    changed_tables: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_sorted_unique_tables(self) -> PrReviewNotification:
        """Keep messages and persisted events deterministic."""
        if self.changed_tables != tuple(sorted(set(self.changed_tables))):
            raise ValueError("changed_tables must be sorted and unique")
        return self


class IndexDoneNotification(NotificationBase):
    """A real index apply and retrieval verification completed."""

    event_type: Literal["index_done"] = "index_done"
    collection: str = Field(min_length=1)
    manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    document_count: int = Field(ge=0)
    chunk_count: int = Field(ge=0)
    upserted_count: int = Field(ge=0)
    deleted_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)


class JobFailedNotification(NotificationBase):
    """An allowlisted GitHub Actions workflow did not complete successfully."""

    event_type: Literal["job_failed"] = "job_failed"
    conclusion: Literal["failure", "timed_out", "cancelled"]
    actor: str = Field(min_length=1)
    attempt: int = Field(gt=0)
    failed_jobs: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_sorted_unique_jobs(self) -> JobFailedNotification:
        """Avoid repeated job names in one operator alert."""
        if self.failed_jobs != tuple(sorted(set(self.failed_jobs))):
            raise ValueError("failed_jobs must be sorted and unique")
        return self


NotificationEvent = Union[
    PrReviewNotification,
    IndexDoneNotification,
    JobFailedNotification,
]
