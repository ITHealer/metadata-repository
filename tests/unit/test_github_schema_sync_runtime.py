"""Mocked GitHub CLI and Git tests for schema-sync PR runtime operations."""

from __future__ import annotations

import json
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any

import pytest

from metadata_pipeline.adapters.github.schema_sync_runtime import (
    GitHubSchemaSyncRuntime,
    SchemaSyncGitHubRuntimeError,
    _parse_porcelain_z,
)
from metadata_pipeline.application.schema_sync_pr import (
    SchemaSyncPullRequestError,
    resolve_active_schema_sync_pull_request,
)
from metadata_pipeline.domain.schema_sync_pr import SchemaSyncPullRequest


@pytest.mark.parametrize("count", (0, 1, 2))
def test_mocked_gh_resolves_zero_one_or_rejects_multiple_open_prs(
    count: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = [
        {
            "number": index + 1,
            "url": f"https://github.example/pr/{index + 1}",
            "headRefName": f"automation/schema-sync-run-{index + 1}",
            "isDraft": True,
        }
        for index in range(count)
    ]
    calls: list[tuple[str, ...]] = []

    def fake_run(command: tuple[str, ...], **_: Any) -> CompletedProcess[str]:
        calls.append(command)
        return CompletedProcess(command, 0, json.dumps(payload), "")

    monkeypatch.setattr(
        "metadata_pipeline.adapters.github.schema_sync_runtime.subprocess.run",
        fake_run,
    )
    candidates = GitHubSchemaSyncRuntime(tmp_path).list_open_pull_requests()

    assert len(candidates) == count
    assert calls[0][:3] == ("gh", "pr", "list")
    assert "automation:schema-sync" in calls[0]
    if count == 2:
        with pytest.raises(SchemaSyncPullRequestError, match="multiple open"):
            resolve_active_schema_sync_pull_request(candidates)
    else:
        assert (resolve_active_schema_sync_pull_request(candidates) is None) == (count == 0)


def test_checkout_merges_main_without_force_or_history_rewrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[tuple[str, ...]] = []

    def fake_run(command: tuple[str, ...], **_: Any) -> CompletedProcess[str]:
        commands.append(command)
        return CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(
        "metadata_pipeline.adapters.github.schema_sync_runtime.subprocess.run",
        fake_run,
    )
    GitHubSchemaSyncRuntime(tmp_path).checkout_and_merge_main(
        SchemaSyncPullRequest(
            number=7,
            url="https://github.example/pr/7",
            head_ref="automation/schema-sync-run-7",
            is_draft=False,
        )
    )

    assert commands[-1] == ("git", "merge", "--no-edit", "origin/main")
    assert all("--force" not in command and "rebase" not in command for command in commands)


def test_main_merge_conflict_fails_without_rewriting_the_active_branch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[tuple[str, ...]] = []

    def fake_run(command: tuple[str, ...], **_: Any) -> CompletedProcess[str]:
        commands.append(command)
        if command[:2] == ("git", "merge"):
            return CompletedProcess(command, 1, "", "merge conflict")
        return CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(
        "metadata_pipeline.adapters.github.schema_sync_runtime.subprocess.run",
        fake_run,
    )

    with pytest.raises(SchemaSyncGitHubRuntimeError, match="merge conflict"):
        GitHubSchemaSyncRuntime(tmp_path).checkout_and_merge_main(
            SchemaSyncPullRequest(
                number=7,
                url="https://github.example/pr/7",
                head_ref="automation/schema-sync-run-7",
                is_draft=True,
            )
        )

    assert commands[-1] == ("git", "merge", "--no-edit", "origin/main")
    assert all("--force" not in command and "rebase" not in command for command in commands)


def test_porcelain_parser_preserves_spaces_and_both_rename_paths() -> None:
    paths = _parse_porcelain_z(
        " M catalog/alpha/review/my file.yml\0"
        "R  catalog/alpha/review/new.yml\0catalog/alpha/review/old.yml\0"
    )

    assert paths == (
        "catalog/alpha/review/my file.yml",
        "catalog/alpha/review/new.yml",
        "catalog/alpha/review/old.yml",
    )


def test_invalid_gh_json_fails_without_falling_back_to_an_empty_list(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: tuple[str, ...], **_: Any) -> CompletedProcess[str]:
        return CompletedProcess(command, 0, "not-json", "")

    monkeypatch.setattr(
        "metadata_pipeline.adapters.github.schema_sync_runtime.subprocess.run",
        fake_run,
    )

    with pytest.raises(SchemaSyncGitHubRuntimeError, match="invalid"):
        GitHubSchemaSyncRuntime(tmp_path).list_open_pull_requests()
