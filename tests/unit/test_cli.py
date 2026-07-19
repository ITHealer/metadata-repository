"""Tests for the foundation CLI."""

from __future__ import annotations

from pathlib import Path
from shutil import copy2
from typing import Any

import pytest
import yaml

from metadata_pipeline import __version__
from metadata_pipeline.cli import main


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
    source = Path("metadata/review/commerce_demo/customers.yml")
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
            "schema/raw/commerce_demo/schema.json",
            "--review-dir",
            str(review_dir),
            "--contract",
            "config/metadata_contract.yml",
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
        "schema/raw/commerce_demo/schema.json",
        "--review-dir",
        str(review_dir),
        "--contract",
        "config/metadata_contract.yml",
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
    for source in Path("metadata/review/commerce_demo").glob("*.yml"):
        copy2(source, review_dir / source.name)
    published_dir = tmp_path / "published"
    chunk_path = tmp_path / "chunks.jsonl"
    common_arguments = [
        "--schema",
        "schema/raw/commerce_demo/schema.json",
        "--review-dir",
        str(review_dir),
        "--contract",
        "config/metadata_contract.yml",
        "--published-dir",
        str(published_dir),
        "--source-review-commit",
        "c" * 40,
    ]

    assert main(["publish", *common_arguments, "--mode", "mock"]) == 0
    assert "publication completed: 3 document(s)" in capsys.readouterr().out
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
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    exit_code = main(
        [
            "publish",
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
