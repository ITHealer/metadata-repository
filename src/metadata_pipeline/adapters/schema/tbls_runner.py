"""Docker Compose adapter for staged tbls documentation and linting."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from metadata_pipeline.domain.catalog import DatabaseProfile
from metadata_pipeline.ports.schema_documenter import SchemaDocumenterError


@dataclass(frozen=True)
class TblsDockerDocumenter:
    """Run the repository-pinned tbls service without starting the demo database."""

    repository_root: Path
    compose_command: tuple[str, ...] = ("docker", "compose")

    def generate(
        self,
        *,
        profile: DatabaseProfile,
        config_path: Path,
        output_dir: Path,
        dsn: str,
    ) -> None:
        """Generate and lint one complete snapshot in a repository-local staging path."""
        root = self.repository_root.resolve()
        config = _relative_to_root(config_path, root, "tbls config")
        output = _relative_to_root(output_dir, root, "tbls output")
        output_dir.mkdir(parents=True, exist_ok=True)
        child_environment = dict(os.environ)
        child_environment.update(
            {
                "TBLS_DSN": dsn,
                "TBLS_DOC_PATH": output.as_posix(),
            }
        )

        common = (
            *self.compose_command,
            "--profile",
            "tools",
            "run",
            "--rm",
            "--no-deps",
            "-e",
            "TBLS_DSN",
            "-e",
            "TBLS_DOC_PATH",
            "tbls",
        )
        self._execute(
            (*common, "doc", "--config", config.as_posix(), "--rm-dist"),
            child_environment,
            dsn,
            profile.key,
            "doc",
        )
        schema_path = output_dir / "schema.json"
        if not schema_path.is_file() or schema_path.stat().st_size == 0:
            raise SchemaDocumenterError(
                f"{profile.key}: tbls did not create a non-empty {schema_path.name}"
            )
        self._execute(
            (*common, "lint", "--config", config.as_posix()),
            child_environment,
            dsn,
            profile.key,
            "lint",
        )

    def _execute(
        self,
        command: Sequence[str],
        environment: Mapping[str, str],
        dsn: str,
        database: str,
        action: str,
    ) -> None:
        """Execute one tbls action and expose a short credential-redacted failure."""
        try:
            completed = subprocess.run(
                command,
                cwd=self.repository_root,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as error:
            raise SchemaDocumenterError(
                f"{database}: unable to start tbls {action}: {error}"
            ) from error
        if completed.returncode == 0:
            return
        detail = (completed.stderr or completed.stdout or "no process output").strip()
        detail = detail.replace(dsn, "<redacted>")
        if len(detail) > 800:
            detail = f"{detail[:800]}..."
        raise SchemaDocumenterError(
            f"{database}: tbls {action} failed with exit code {completed.returncode}: {detail}"
        )


def _relative_to_root(path: Path, root: Path, label: str) -> Path:
    """Reject paths outside the mounted repository before starting Docker."""
    try:
        return path.resolve().relative_to(root)
    except ValueError as error:
        raise SchemaDocumenterError(f"{label} must be inside repository root {root}") from error
