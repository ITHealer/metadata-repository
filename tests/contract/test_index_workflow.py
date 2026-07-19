"""Post-merge index artifact workflow contract."""

from pathlib import Path

WORKFLOW = Path(".github/workflows/index.yml")


def test_index_workflow_runs_only_after_main_published_changes() -> None:
    content = WORKFLOW.read_text(encoding="utf-8")

    assert "  push:\n    branches:\n      - main" in content
    assert "      - knowledge/published/**" in content
    assert "pull_request:" not in content
    assert "  contents: read" in content
    assert "make index-build" in content
    assert "make retrieval-smoke" in content


def test_index_workflow_uploads_manifest_actions_and_report() -> None:
    content = WORKFLOW.read_text(encoding="utf-8")

    assert "build/index/manifest.json" in content
    assert "build/index/actions.json" in content
    assert "build/index/retrieval-report.json" in content
    assert "if-no-files-found: error" in content
    assert "retention-days: 30" in content
