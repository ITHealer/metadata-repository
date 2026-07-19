"""Security and rollout contract for manual live gateway UAT."""

from pathlib import Path

WORKFLOW = Path(".github/workflows/live-llm-uat.yml")


def test_live_uat_is_manual_gated_and_read_only() -> None:
    content = WORKFLOW.read_text(encoding="utf-8")

    assert "  workflow_dispatch:\n" in content
    assert "pull_request:" not in content
    assert "push:" not in content
    assert "vars.ENABLE_LIVE_LLM_UAT == 'true'" in content
    assert "  contents: read" in content
    assert "secrets.OPENAI_API_KEY" in content


def test_live_uat_uses_gateway_configuration_and_isolated_artifacts() -> None:
    content = WORKFLOW.read_text(encoding="utf-8")

    assert "https://ai-gateway.dev/v1" in content
    assert "OPENAI_MODEL: ${{ inputs.model }}" in content
    assert 'OPENAI_MAX_RETRIES: "2"' in content
    assert "make verify" in content
    assert "make live-uat" in content
    assert "build/live/published/commerce_demo" in content
