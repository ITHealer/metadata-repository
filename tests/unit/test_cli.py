"""Tests for the foundation CLI."""

from __future__ import annotations

import json
from pathlib import Path
from shutil import copy2
from typing import Any

import pytest
import yaml

from metadata_pipeline import __version__
from metadata_pipeline.adapters.index.manifest import ManifestIndexStore
from metadata_pipeline.cli import main
from metadata_pipeline.domain.index import IndexManifest
from metadata_pipeline.domain.schema_sync import (
    DatabaseSchemaSyncReport,
    ScheduledSchemaSyncReport,
    SchemaSyncOutcome,
)
from metadata_pipeline.domain.schema_sync_pr import (
    SchemaSyncPullRequest,
    SchemaSyncPullRequestState,
)
from metadata_pipeline.domain.vector_apply import ApplyOutcome, VectorApplySummary
from metadata_pipeline.io.apply_summary_json import write_apply_summary
from metadata_pipeline.io.schema_sync_pr_state_json import write_schema_sync_pr_state
from metadata_pipeline.io.schema_sync_report_json import write_schema_sync_report

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PUBLICATION_ARGS = (
    "--schema",
    str(ROOT / "tests/fixtures/commerce_demo/schema.json"),
    "--review-dir",
    str(ROOT / "tests/fixtures/commerce_demo/review"),
    "--contract",
    str(ROOT / "contracts/metadata_contract.yml"),
)


def test_cli_shows_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as error:
        main(["--version"])

    assert error.value.code == 0
    assert capsys.readouterr().out.strip() == f"metadata {__version__}"


def test_cli_doctor_accepts_supported_python(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["doctor"]) == 0

    output = capsys.readouterr().out
    assert "status=ok" in output
    assert "minimum=3.9" in output


def test_cli_without_command_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "Manage the ClickHouse metadata review pipeline" in capsys.readouterr().out


def test_validate_review_returns_failure_for_unknown_table(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    review_dir = tmp_path / "review"
    review_dir.mkdir()
    source = Path("tests/fixtures/commerce_demo/review/customers.yml")
    payload: dict[str, Any] = yaml.safe_load(source.read_text(encoding="utf-8"))
    payload["table"] = "customers_typo"
    (review_dir / "customers.yml").write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "validate-review",
            "--schema",
            "tests/fixtures/commerce_demo/schema.json",
            "--review-dir",
            str(review_dir),
            "--contract",
            "contracts/metadata_contract.yml",
        ]
    )

    assert exit_code == 1
    assert "unknown_table" in capsys.readouterr().err


def test_draft_cli_is_idempotent_and_warning_only_validation_passes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    review_dir = tmp_path / "review"
    common_arguments = [
        "--schema",
        "tests/fixtures/commerce_demo/schema.json",
        "--review-dir",
        str(review_dir),
        "--contract",
        "contracts/metadata_contract.yml",
    ]

    assert main(["draft", *common_arguments]) == 0
    assert "customers: created" in capsys.readouterr().out
    assert main(["draft", *common_arguments]) == 0
    assert "customers: unchanged" in capsys.readouterr().out
    assert main(["validate-review", *common_arguments]) == 0

    output = capsys.readouterr()
    assert "warning: missing_sensitivity_classification" in output.err
    assert "review metadata validation passed" in output.out


def test_publish_validate_and_chunk_commands_share_one_contract(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    review_dir = tmp_path / "review"
    review_dir.mkdir()
    for source in Path("tests/fixtures/commerce_demo/review").glob("*.yml"):
        copy2(source, review_dir / source.name)
    published_dir = tmp_path / "published"
    chunk_path = tmp_path / "chunks.jsonl"
    common_arguments = [
        "--schema",
        "tests/fixtures/commerce_demo/schema.json",
        "--review-dir",
        str(review_dir),
        "--contract",
        "contracts/metadata_contract.yml",
        "--published-dir",
        str(published_dir),
        "--source-review-commit",
        "c" * 40,
    ]

    assert (
        main(
            [
                "publish",
                *common_arguments,
                "--mode",
                "mock",
                "--chunk-output",
                str(chunk_path),
            ]
        )
        == 0
    )
    publish_output = capsys.readouterr().out
    assert "publication completed: 3 document(s)" in publish_output
    assert "chunk artifact updated" in publish_output
    assert len(chunk_path.read_text(encoding="utf-8").splitlines()) == 26
    assert main(["validate-published", *common_arguments]) == 0
    assert "published validation passed" in capsys.readouterr().out
    assert (
        main(
            [
                "chunk",
                *common_arguments,
                "--mode",
                "mock",
                "--dry-run",
                "--output",
                str(chunk_path),
            ]
        )
        == 0
    )
    assert "26 chunk(s)" in capsys.readouterr().out
    assert len(chunk_path.read_text(encoding="utf-8").splitlines()) == 26


def test_live_publish_requires_gateway_key(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    exit_code = main(
        [
            "publish",
            *FIXTURE_PUBLICATION_ARGS,
            "--repository-root",
            str(ROOT),
            "--published-dir",
            str(tmp_path / "published"),
            "--source-review-commit",
            "d" * 40,
            "--mode",
            "live",
        ]
    )

    assert exit_code == 1
    assert "OPENAI_API_KEY" in capsys.readouterr().err


def test_publish_can_select_one_table_without_deleting_other_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    published_dir = tmp_path / "published"
    published_dir.mkdir()
    untouched = published_dir / "customers.md"
    untouched.write_text("existing generated document\n", encoding="utf-8")
    chunks = tmp_path / "orders.jsonl"

    exit_code = main(
        [
            "publish",
            *FIXTURE_PUBLICATION_ARGS,
            "--published-dir",
            str(published_dir),
            "--source-review-commit",
            "e" * 40,
            "--mode",
            "mock",
            "--table",
            "orders",
            "--chunk-output",
            str(chunks),
        ]
    )

    assert exit_code == 0
    assert "publication completed: 1 document(s)" in capsys.readouterr().out
    assert untouched.read_text(encoding="utf-8") == "existing generated document\n"
    assert (published_dir / "orders.md").exists()
    assert not (published_dir / "order_items.md").exists()
    assert {
        json.loads(line)["table"] for line in chunks.read_text(encoding="utf-8").splitlines()
    } == {"orders"}


def test_publish_rejects_unknown_selected_table(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    published_dir = tmp_path / "published"

    exit_code = main(
        [
            "publish",
            *FIXTURE_PUBLICATION_ARGS,
            "--published-dir",
            str(published_dir),
            "--source-review-commit",
            "f" * 40,
            "--mode",
            "mock",
            "--table",
            "missing_table",
        ]
    )

    assert exit_code == 1
    assert "unknown_selected_table" in capsys.readouterr().err
    assert not published_dir.exists()


def test_scheduled_sync_disabled_writes_a_machine_readable_no_work_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SCHEMA_SYNC_ENABLED", "false")
    report_path = tmp_path / "build/schema-sync/report.json"
    pr_body_path = tmp_path / "build/schema-sync/pr-body.md"

    exit_code = main(
        [
            "scheduled-sync",
            "--repository-root",
            str(tmp_path),
            "--report",
            str(report_path),
            "--pr-body",
            str(pr_body_path),
            "--run-id",
            "unit-test",
        ]
    )

    assert exit_code == 0
    assert json.loads(report_path.read_text(encoding="utf-8"))["outcome"] == "disabled"
    assert "No reviewer file requires changes" in pr_body_path.read_text(encoding="utf-8")
    assert "scheduled schema sync disabled" in capsys.readouterr().out


def test_schema_sync_pr_publish_skips_noop_without_calling_git_or_gh(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    state_path = tmp_path / "pr-state.json"
    state_path.write_text(
        '{"format_version":"schema-sync-pr-state-v1","active":null}\n',
        encoding="utf-8",
    )
    report_path = tmp_path / "report.json"
    report_path.write_text(
        '{"format_version":"schema-sync-report-v1","run_id":"unit",'
        '"outcome":"noop","databases":[],"warnings":[],"manual_cleanup":[]}\n',
        encoding="utf-8",
    )

    exit_code = main(
        [
            "schema-sync-pr-publish",
            "--repository-root",
            str(tmp_path),
            "--state",
            str(state_path),
            "--report",
            str(report_path),
            "--pr-body",
            str(tmp_path / "pr-body.md"),
            "--run-id",
            "unit",
        ]
    )

    assert exit_code == 0
    assert "publish skipped: outcome=noop" in capsys.readouterr().out


@pytest.mark.parametrize("existing_pr", (False, True))
def test_schema_sync_pr_publish_creates_or_updates_one_pr(
    existing_pr: bool,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline: dict[str, Any] = json.loads(
        (ROOT / "tests/fixtures/commerce_demo/schema.json").read_text(encoding="utf-8")
    )
    baseline["name"] = "alpha"
    current: dict[str, Any] = json.loads(json.dumps(baseline))
    customers = next(table for table in current["tables"] if table["name"] == "customers")
    customers["comment"] = "Changed customer contract"
    schema_path = tmp_path / "catalog/alpha/generated/raw/schema.json"
    schema_path.parent.mkdir(parents=True)
    schema_path.write_text(json.dumps(current), encoding="utf-8")
    active = (
        SchemaSyncPullRequest(
            number=17,
            url="https://github.example/pr/17",
            head_ref="automation/schema-sync-existing",
            is_draft=False,
        )
        if existing_pr
        else None
    )
    state_path = tmp_path / "build/schema-sync/pr-state.json"
    write_schema_sync_pr_state(state_path, SchemaSyncPullRequestState(active=active))
    report_path = tmp_path / "build/schema-sync/report.json"
    write_schema_sync_report(
        report_path,
        ScheduledSchemaSyncReport(
            run_id="123-1",
            outcome=SchemaSyncOutcome.CHANGED,
            databases=(
                DatabaseSchemaSyncReport(
                    key="alpha",
                    clickhouse_database="alpha",
                    modified=("customers",),
                ),
            ),
        ),
    )
    actions: list[str] = []

    class FakeRuntime:
        def __init__(self, _: Path) -> None:
            pass

        def worktree_paths(self) -> tuple[str, ...]:
            return (
                "catalog/alpha/generated/raw/schema.json",
                "catalog/alpha/review/customers.yml",
            )

        def create_branch(self, branch: str) -> None:
            actions.append(f"create:{branch}")

        def commit_schema_sync(self) -> str:
            actions.append("commit")
            return "c" * 40

        def read_text_at_revision(self, revision: str, path: str) -> str:
            assert revision == "origin/main"
            assert path == "catalog/alpha/generated/raw/schema.json"
            return json.dumps(baseline)

        def cumulative_changed_paths(self) -> tuple[str, ...]:
            return (
                "catalog/alpha/generated/raw/schema.json",
                "catalog/alpha/review/customers.yml",
            )

        def push(self, branch: str) -> None:
            actions.append(f"push:{branch}")

        def create_draft_pull_request(self, *, branch: str, body_path: Path) -> str:
            assert body_path.is_file()
            actions.append(f"open:{branch}")
            return "https://github.example/pr/18"

        def update_pull_request_body(self, number: int, body_path: Path) -> None:
            assert body_path.is_file()
            actions.append(f"update:{number}")

    monkeypatch.setattr("metadata_pipeline.cli.GitHubSchemaSyncRuntime", FakeRuntime)
    github_output = tmp_path / "github-output.txt"

    exit_code = main(
        [
            "schema-sync-pr-publish",
            "--repository-root",
            str(tmp_path),
            "--state",
            str(state_path),
            "--report",
            str(report_path),
            "--pr-body",
            str(tmp_path / "build/schema-sync/pr-body.md"),
            "--run-id",
            "123-1",
            "--github-output",
            str(github_output),
        ]
    )

    assert exit_code == 0
    branch = "automation/schema-sync-existing" if existing_pr else "automation/schema-sync-123-1"
    assert f"push:{branch}" in actions
    assert ("update:17" in actions) is existing_pr
    assert (f"open:{branch}" in actions) is (not existing_pr)
    assert (f"create:{branch}" in actions) is (not existing_pr)
    assert f"action={'updated' if existing_pr else 'created'}" in github_output.read_text(
        encoding="utf-8"
    )
    assert "schema-sync PR" in capsys.readouterr().out


def test_cli_builds_pr_review_event_and_disabled_delivery_is_a_noop(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report_path = tmp_path / "report.json"
    write_schema_sync_report(
        report_path,
        ScheduledSchemaSyncReport(
            run_id="123-1",
            outcome=SchemaSyncOutcome.CHANGED,
            databases=(
                DatabaseSchemaSyncReport(
                    key="commerce_demo",
                    clickhouse_database="commerce_demo",
                    added=("payments",),
                    modified=("orders",),
                ),
            ),
        ),
    )
    event_path = tmp_path / "notification.json"
    commit = "a" * 40

    assert (
        main(
            [
                "build-pr-review-notification",
                "--report",
                str(report_path),
                "--action",
                "created",
                "--pr-number",
                "28",
                "--pr-url",
                "https://github.example/pr/28",
                "--repository",
                "acme/metadata",
                "--branch",
                "automation/schema-sync-123-1",
                "--commit",
                commit,
                "--workflow",
                "Scheduled Schema Sync",
                "--run-url",
                "https://github.example/runs/123",
                "--output",
                str(event_path),
            ]
        )
        == 0
    )
    payload = json.loads(event_path.read_text(encoding="utf-8"))
    assert payload["event_id"] == f"pr_review:{commit}"
    assert payload["changed_tables"] == ["commerce_demo.orders", "commerce_demo.payments"]

    monkeypatch.setenv("TELEGRAM_NOTIFICATIONS_ENABLED", "false")
    assert main(["notify", "--event-file", str(event_path)]) == 0
    assert "notification disabled: pr_review" in capsys.readouterr().out


def test_cli_builds_job_failed_event_from_job_name_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    failed_jobs = tmp_path / "failed-jobs.txt"
    failed_jobs.write_text("Unit tests\nLint; echo not-shell\nUnit tests\n", encoding="utf-8")
    output = tmp_path / "job-failed.json"

    exit_code = main(
        [
            "build-job-failed-notification",
            "--run-id",
            "123",
            "--attempt",
            "2",
            "--conclusion",
            "failure",
            "--failed-jobs-file",
            str(failed_jobs),
            "--actor",
            "octocat",
            "--repository",
            "acme/metadata",
            "--branch",
            "feature/test",
            "--commit",
            "b" * 40,
            "--workflow",
            "Quality",
            "--run-url",
            "https://github.example/runs/123",
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["event_id"] == "job_failed:123:2:failure"
    assert payload["failed_jobs"] == ["Lint; echo not-shell", "Unit tests"]
    assert "job_failed event written" in capsys.readouterr().out


def test_cli_disabled_vector_apply_writes_a_non_mutating_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path = tmp_path / "manifest.json"
    ManifestIndexStore(manifest_path).save(IndexManifest.create(source_commit="a" * 40))
    summary_path = tmp_path / "apply-summary.json"
    monkeypatch.setenv("INDEX_APPLY_ENABLED", "false")

    assert (
        main(
            [
                "apply-index",
                "--manifest",
                str(manifest_path),
                "--summary",
                str(summary_path),
            ]
        )
        == 0
    )
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["outcome"] == "disabled"
    assert payload["verified"] is False
    assert "vector index apply disabled" in capsys.readouterr().out


def test_cli_builds_index_done_only_from_verified_changed_apply(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    summary_path = tmp_path / "apply-summary.json"
    write_apply_summary(
        summary_path,
        VectorApplySummary(
            outcome=ApplyOutcome.APPLIED,
            collection="metadata__gemini_embedding_001__768",
            manifest_hash="b" * 64,
            document_count=3,
            chunk_count=22,
            upserted_count=2,
            deleted_count=1,
            skipped_count=20,
            verified=True,
        ),
    )
    output = tmp_path / "index-done.json"

    assert (
        main(
            [
                "build-index-done-notification",
                "--summary",
                str(summary_path),
                "--repository",
                "acme/metadata",
                "--branch",
                "main",
                "--commit",
                "c" * 40,
                "--workflow",
                "Apply Vector Index",
                "--run-url",
                "https://github.example/runs/9",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["event_type"] == "index_done"
    assert payload["skipped_count"] == 20
    assert "index_done event written" in capsys.readouterr().out
