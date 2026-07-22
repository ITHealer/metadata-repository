"""Contracts for the single active scheduled schema-sync Pull Request."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field

from metadata_pipeline.domain.review import StrictModel


class SchemaSyncPullRequest(StrictModel):
    """The minimum non-secret GitHub PR state needed by the scheduled runtime."""

    number: int = Field(gt=0)
    url: str = Field(pattern=r"^https://")
    head_ref: str = Field(pattern=r"^automation/schema-sync-[A-Za-z0-9._-]+$")
    is_draft: bool


class SchemaSyncPullRequestState(StrictModel):
    """Stable handoff from the prepare step to the publish step."""

    format_version: Literal["schema-sync-pr-state-v1"] = "schema-sync-pr-state-v1"
    active: Optional[SchemaSyncPullRequest] = None  # noqa: UP007 - Python 3.9 support
