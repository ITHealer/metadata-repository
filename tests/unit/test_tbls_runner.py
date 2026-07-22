"""Tests for the credential-safe Docker tbls adapter."""

from pathlib import Path
from subprocess import CompletedProcess
from typing import Any

import pytest

from metadata_pipeline.adapters.schema.tbls_runner import TblsDockerDocumenter
from metadata_pipeline.domain.catalog import DatabaseProfile
from metadata_pipeline.ports.schema_documenter import SchemaDocumenterError


def _profile() -> DatabaseProfile:
    return DatabaseProfile(
        enabled=True,
        scheduled_sync=True,
        tbls_dsn_env="TBLS_DSN_EXAMPLE",
        key="example",
        display_name="Example",
        clickhouse_database="example",
        description="Test profile",
        tables=("events",),
    )


def test_runs_doc_and_lint_without_putting_dsn_in_argv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = tmp_path / "config/databases/example/tbls.yml"
    config.parent.mkdir(parents=True)
    config.write_text("name: example\n", encoding="utf-8")
    calls: list[tuple[tuple[str, ...], dict[str, str]]] = []

    def fake_run(command: tuple[str, ...], **kwargs: Any) -> CompletedProcess[str]:
        environment = dict(kwargs["env"])
        calls.append((tuple(command), environment))
        if "doc" in command:
            output = tmp_path / environment["TBLS_DOC_PATH"]
            output.mkdir(parents=True, exist_ok=True)
            output.joinpath("schema.json").write_text("{}\n", encoding="utf-8")
        return CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("metadata_pipeline.adapters.schema.tbls_runner.subprocess.run", fake_run)
    documenter = TblsDockerDocumenter(tmp_path)
    dsn = "clickhouse://readonly:secret@clickhouse.internal:9000/example"

    documenter.generate(
        profile=_profile(),
        config_path=config,
        output_dir=tmp_path / "build/schema-sync/example/raw",
        dsn=dsn,
    )

    assert len(calls) == 2
    assert "doc" in calls[0][0]
    assert "lint" in calls[1][0]
    assert "--no-deps" in calls[0][0]
    assert dsn not in calls[0][0]
    assert calls[0][1]["TBLS_DSN"] == dsn
    assert calls[0][1]["TBLS_DOC_PATH"] == "build/schema-sync/example/raw"


def test_redacts_dsn_from_process_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = tmp_path / "config/databases/example/tbls.yml"
    config.parent.mkdir(parents=True)
    config.write_text("name: example\n", encoding="utf-8")
    dsn = "clickhouse://readonly:super-secret@clickhouse.internal/example"

    def fake_run(command: tuple[str, ...], **_: Any) -> CompletedProcess[str]:
        return CompletedProcess(command, 1, "", f"connection failed for {dsn}")

    monkeypatch.setattr("metadata_pipeline.adapters.schema.tbls_runner.subprocess.run", fake_run)

    with pytest.raises(SchemaDocumenterError, match="<redacted>") as error:
        TblsDockerDocumenter(tmp_path).generate(
            profile=_profile(),
            config_path=config,
            output_dir=tmp_path / "build/schema-sync/example/raw",
            dsn=dsn,
        )

    assert dsn not in str(error.value)
    assert "super-secret" not in str(error.value)


def test_rejects_output_outside_repository_before_starting_docker(tmp_path: Path) -> None:
    config = tmp_path / "config/databases/example/tbls.yml"
    config.parent.mkdir(parents=True)
    config.write_text("name: example\n", encoding="utf-8")

    with pytest.raises(SchemaDocumenterError, match="must be inside repository root"):
        TblsDockerDocumenter(tmp_path).generate(
            profile=_profile(),
            config_path=config,
            output_dir=tmp_path.parent / "outside/raw",
            dsn="clickhouse://secret",
        )
