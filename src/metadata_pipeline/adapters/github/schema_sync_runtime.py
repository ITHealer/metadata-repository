"""Credential-safe Git and GitHub CLI operations for scheduled schema-sync PRs."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from metadata_pipeline.domain.schema_sync_pr import SchemaSyncPullRequest

RAW_PATHSPEC = ":(glob)catalog/*/generated/raw/**"
REVIEW_PATHSPEC = ":(glob)catalog/*/review/**"


class SchemaSyncGitHubRuntimeError(RuntimeError):
    """Raised when a Git or GitHub CLI operation cannot complete safely."""


@dataclass(frozen=True)
class GitHubSchemaSyncRuntime:
    """Run explicit argv-only Git and gh commands inside one repository checkout."""

    repository_root: Path

    def list_open_pull_requests(
        self,
        *,
        label: str = "automation:schema-sync",
    ) -> tuple[SchemaSyncPullRequest, ...]:
        """List open schema-sync PRs targeting main without returning response extras."""
        completed = self._run(
            (
                "gh",
                "pr",
                "list",
                "--state",
                "open",
                "--base",
                "main",
                "--label",
                label,
                "--limit",
                "10",
                "--json",
                "number,url,headRefName,isDraft",
            )
        )
        try:
            payload = json.loads(completed.stdout)
            if not isinstance(payload, list):
                raise ValueError("expected a JSON array")
            return tuple(
                SchemaSyncPullRequest(
                    number=item["number"],
                    url=item["url"],
                    head_ref=item["headRefName"],
                    is_draft=item["isDraft"],
                )
                for item in payload
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, ValidationError) as error:
            raise SchemaSyncGitHubRuntimeError(
                "gh returned invalid schema-sync Pull Request JSON"
            ) from error

    def checkout_and_merge_main(self, pull_request: SchemaSyncPullRequest) -> None:
        """Check out the existing bot branch and merge current main without rewriting history."""
        branch = pull_request.head_ref
        self._run(
            (
                "git",
                "fetch",
                "--no-tags",
                "origin",
                "refs/heads/main:refs/remotes/origin/main",
            )
        )
        self._run(
            (
                "git",
                "fetch",
                "--no-tags",
                "origin",
                f"refs/heads/{branch}:refs/remotes/origin/{branch}",
            )
        )
        self._run(("git", "switch", "--create", branch, "--track", f"origin/{branch}"))
        self._run(("git", "merge", "--no-edit", "origin/main"))

    def worktree_paths(self) -> tuple[str, ...]:
        """Return modified and untracked paths from NUL-delimited porcelain output."""
        completed = self._run(("git", "status", "--porcelain=v1", "-z", "--untracked-files=all"))
        return _parse_porcelain_z(completed.stdout)

    def create_branch(self, branch: str) -> None:
        """Create a new local automation branch only after a schema change exists."""
        self._run(("git", "switch", "--create", branch))

    def commit_schema_sync(self) -> str:
        """Commit only allowlisted source artifacts and return the new commit SHA."""
        self._run(("git", "config", "user.name", "metadata-bot"))
        self._run(("git", "config", "user.email", "metadata-bot@users.noreply.github.com"))
        self._run(("git", "add", "--", RAW_PATHSPEC, REVIEW_PATHSPEC))
        self._run(("git", "commit", "-m", "chore(schema): synchronize ClickHouse metadata"))
        return self._run(("git", "rev-parse", "HEAD")).stdout.strip()

    def cumulative_changed_paths(self, base_ref: str = "origin/main") -> tuple[str, ...]:
        """Return the complete PR diff used to build a cumulative reviewer summary."""
        completed = self._run(
            (
                "git",
                "diff",
                "--name-only",
                "-z",
                f"{base_ref}...HEAD",
                "--",
                RAW_PATHSPEC,
                REVIEW_PATHSPEC,
            )
        )
        return tuple(sorted(path for path in completed.stdout.split("\0") if path))

    def read_text_at_revision(self, revision: str, path: str) -> str | None:
        """Read one Git blob, returning None when the path did not exist at that revision."""
        exists = self._run(("git", "cat-file", "-e", f"{revision}:{path}"), check=False)
        if exists.returncode != 0:
            return None
        return self._run(("git", "show", f"{revision}:{path}")).stdout

    def push(self, branch: str) -> None:
        """Push without force so concurrent reviewer or bot changes fail safely."""
        self._run(("git", "push", "origin", f"HEAD:{branch}"))

    def create_draft_pull_request(
        self,
        *,
        branch: str,
        body_path: Path,
        label: str = "automation:schema-sync",
    ) -> str:
        """Create and label a new Draft PR, returning its URL."""
        created = self._run(
            (
                "gh",
                "pr",
                "create",
                "--draft",
                "--base",
                "main",
                "--head",
                branch,
                "--title",
                "chore(schema): synchronize ClickHouse metadata",
                "--body-file",
                str(body_path),
                "--label",
                label,
            )
        )
        url = created.stdout.strip()
        if not url.startswith("https://"):
            raise SchemaSyncGitHubRuntimeError("gh pr create did not return a Pull Request URL")
        return url

    def update_pull_request_body(self, number: int, body_path: Path) -> None:
        """Update only the body; preserve the reviewer's current Draft/Ready state."""
        self._run(("gh", "pr", "edit", str(number), "--body-file", str(body_path)))

    def _run(
        self,
        command: tuple[str, ...],
        *,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        try:
            completed = subprocess.run(
                command,
                cwd=self.repository_root,
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as error:
            raise SchemaSyncGitHubRuntimeError(
                f"unable to start {command[0]} command: {error}"
            ) from error
        if check and completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "no process output").strip()
            if len(detail) > 800:
                detail = f"{detail[:800]}..."
            raise SchemaSyncGitHubRuntimeError(
                f"{command[0]} command failed with exit code {completed.returncode}: {detail}"
            )
        return completed


def _parse_porcelain_z(payload: str) -> tuple[str, ...]:
    """Parse stable Git porcelain without breaking paths that contain whitespace."""
    tokens = payload.rstrip("\0").split("\0") if payload else []
    paths: list[str] = []
    index = 0
    while index < len(tokens):
        entry = tokens[index]
        if len(entry) < 4 or entry[2] != " ":
            raise SchemaSyncGitHubRuntimeError("git returned invalid porcelain status output")
        status = entry[:2]
        paths.append(entry[3:])
        index += 1
        if "R" in status or "C" in status:
            if index >= len(tokens):
                raise SchemaSyncGitHubRuntimeError("git returned an incomplete rename status")
            paths.append(tokens[index])
            index += 1
    return tuple(sorted(set(paths)))
