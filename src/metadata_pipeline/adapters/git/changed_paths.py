"""Read normalized name-status changes from Git without shell interpolation."""

from __future__ import annotations

import subprocess
from pathlib import Path

from metadata_pipeline.application.classify_changes import ChangedPath


class GitDiffError(RuntimeError):
    """Raised when Git cannot resolve or compare the requested revisions."""


def read_changed_paths(
    base: str,
    head: str,
    repository: Path = Path("."),
) -> tuple[ChangedPath, ...]:
    """Return A/M/D/R/C entries from a three-dot Git diff."""
    try:
        result = subprocess.run(
            ("git", "diff", "--name-status", "-z", "--find-renames", f"{base}...{head}"),
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        detail = getattr(error, "stderr", "") or str(error)
        raise GitDiffError(
            f"cannot compare Git revisions {base!r} and {head!r}: {detail}"
        ) from error
    return parse_name_status_z(result.stdout)


def read_commit_changes(commit: str, repository: Path = Path(".")) -> tuple[ChangedPath, ...]:
    """Return only changes introduced by one commit, including merge-safe parent diff."""
    try:
        result = subprocess.run(
            ("git", "diff-tree", "--no-commit-id", "--name-status", "-r", "-z", commit),
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        detail = getattr(error, "stderr", "") or str(error)
        raise GitDiffError(f"cannot inspect Git commit {commit!r}: {detail}") from error
    return parse_name_status_z(result.stdout)


def parse_name_status_z(payload: str) -> tuple[ChangedPath, ...]:
    """Parse Git's NUL-delimited format without breaking whitespace in paths."""
    tokens = payload.rstrip("\0").split("\0") if payload else []
    changes: list[ChangedPath] = []
    index = 0
    while index < len(tokens):
        status = tokens[index]
        index += 1
        if status.startswith(("R", "C")):
            if index + 1 >= len(tokens):
                raise GitDiffError(f"incomplete rename/copy entry for status {status!r}")
            previous_path, path = tokens[index : index + 2]
            index += 2
            changes.append(ChangedPath(status=status, path=path, previous_path=previous_path))
            continue
        if index >= len(tokens):
            raise GitDiffError(f"missing path for status {status!r}")
        changes.append(ChangedPath(status=status, path=tokens[index]))
        index += 1
    return tuple(changes)
