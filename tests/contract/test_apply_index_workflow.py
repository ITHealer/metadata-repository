"""Safety contract for VectorDB apply and post-apply notification."""

from pathlib import Path

WORKFLOW = Path(".github/workflows/apply-index.yml")


def test_apply_workflow_is_disabled_by_default_and_main_only() -> None:
    content = WORKFLOW.read_text(encoding="utf-8")

    assert content.startswith("name: Apply Vector Index\n")
    assert "      - main" in content
    assert "if: vars.INDEX_APPLY_ENABLED == 'true'" in content
    assert 'INDEX_APPLY_ENABLED: "true"' in content
    assert "bootstrap_collection:" in content
    assert "inputs.bootstrap_collection" in content
    assert "pull_request:" not in content


def test_index_done_is_strictly_after_apply_and_retrieval_verification() -> None:
    content = WORKFLOW.read_text(encoding="utf-8")

    apply_position = content.index("Apply and verify actual VectorDB state")
    retrieval_position = content.index("Verify live semantic retrieval")
    event_position = content.index("Build verified index_done event")
    notify_position = content.index("Notify knowledge-base update through Telegram")
    assert apply_position < retrieval_position < event_position < notify_position
    assert "steps.apply.outputs.changed == 'true'" in content
    assert "build-index-done-notification" in content
    assert "./scripts/metadata notify" in content


def test_apply_workflow_maps_secrets_directly_and_never_commits_artifacts() -> None:
    content = WORKFLOW.read_text(encoding="utf-8")

    assert "GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}" in content
    assert "QDRANT_URL: ${{ secrets.QDRANT_URL }}" in content
    assert "QDRANT_API_KEY: ${{ secrets.QDRANT_API_KEY }}" in content
    assert "git commit" not in content
    assert "git push" not in content
