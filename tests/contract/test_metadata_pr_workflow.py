"""Security and loop-prevention contract for the metadata PR workflow."""

from pathlib import Path

WORKFLOW = Path(".github/workflows/metadata-pr.yml")


def test_workflow_uses_safe_pull_request_boundary_and_stable_gate() -> None:
    content = WORKFLOW.read_text(encoding="utf-8")

    assert content.startswith("name: Metadata PR\n")
    assert "  pull_request:\n" in content
    assert "pull_request_target" not in content
    assert "  contents: read\n" in content
    assert "  pr-gate:\n" in content
    assert "    name: pr-gate\n" in content
    assert "metadata-pr-${{ github.event.pull_request.number }}" in content


def test_workflow_guards_bot_output_and_fork_secrets() -> None:
    content = WORKFLOW.read_text(encoding="utf-8")

    assert "secrets.METADATA_BOT_TOKEN || github.token" in content
    assert "github.event.pull_request.head.repo.full_name == github.repository" in content
    assert "steps.changes.outputs.latest_only_published" in content
    assert "steps.decision.outputs.mode == 'reject-published'" in content
    assert 'unexpected="$(git status --porcelain' in content
    assert 'git push origin "HEAD:$HEAD_BRANCH"' in content
