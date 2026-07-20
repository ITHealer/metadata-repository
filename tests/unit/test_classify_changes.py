"""Unit tests for Git path parsing and metadata workflow classification."""

from pathlib import Path

import pytest

from metadata_pipeline.adapters.git.changed_paths import GitDiffError, parse_name_status_z
from metadata_pipeline.application.classify_changes import (
    ChangedPath,
    classify_changed_paths,
)
from metadata_pipeline.cli import main


def test_path_matrix_classifies_inputs_outputs_and_unrelated_changes() -> None:
    classification = classify_changed_paths(
        (
            ChangedPath("M", "catalog/commerce_demo/review/orders.yml"),
            ChangedPath("A", "catalog/commerce_demo/generated/raw/order_events.md"),
            ChangedPath("M", "catalog/commerce_demo/generated/published/orders.md"),
            ChangedPath("M", "src/metadata_pipeline/domain/published.py"),
            ChangedPath("M", "README.md"),
        )
    )

    assert classification.total == 5
    assert classification.input_count == 3
    assert classification.generation_source_count == 1
    assert classification.has_generation_sources is True
    assert classification.published_count == 1
    assert classification.unrelated_count == 1
    assert classification.has_inputs is True
    assert classification.has_published is True
    assert classification.only_published is False


def test_only_published_requires_nonempty_allowlisted_change_set() -> None:
    empty = classify_changed_paths(())
    published = classify_changed_paths(
        (ChangedPath("M", "catalog/commerce_demo/generated/published/orders.md"),)
    )

    assert empty.only_published is False
    assert published.only_published is True
    assert published.github_outputs("latest_")["latest_only_published"] == "true"


def test_rename_checks_both_old_and_new_paths() -> None:
    changes = parse_name_status_z(
        "R100\0catalog/commerce_demo/generated/published/orders.md\0docs/orders.md\0"
    )

    assert changes == (
        ChangedPath(
            "R100",
            "docs/orders.md",
            "catalog/commerce_demo/generated/published/orders.md",
        ),
    )
    assert classify_changed_paths(changes).has_published is True


def test_parser_rejects_incomplete_git_entry() -> None:
    with pytest.raises(GitDiffError, match="incomplete rename"):
        parse_name_status_z("R100\0old.md\0")


def test_classify_changes_cli_writes_github_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "metadata_pipeline.cli.read_changed_paths",
        lambda base, head: (ChangedPath("M", "catalog/commerce_demo/review/orders.yml"),),
    )
    monkeypatch.setattr(
        "metadata_pipeline.cli.read_commit_changes",
        lambda head: (ChangedPath("M", "catalog/commerce_demo/generated/published/orders.md"),),
    )
    output = tmp_path / "github-output"

    assert (
        main(
            [
                "classify-changes",
                "--base",
                "base-sha",
                "--head",
                "head-sha",
                "--github-output",
                str(output),
            ]
        )
        == 0
    )

    values = dict(line.split("=", 1) for line in output.read_text(encoding="utf-8").splitlines())
    assert values["pr_has_inputs"] == "true"
    assert values["pr_has_generation_sources"] == "false"
    assert values["latest_only_published"] == "true"
    assert '"latest_only_published": "true"' in capsys.readouterr().out
