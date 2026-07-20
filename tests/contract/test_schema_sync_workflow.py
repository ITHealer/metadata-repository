"""Safety contract for scheduled/manual schema synchronization."""

from pathlib import Path

WORKFLOW = Path(".github/workflows/schema-sync.yml")


def test_schema_sync_is_manual_first_and_never_pushes_main() -> None:
    content = WORKFLOW.read_text(encoding="utf-8")

    assert "  workflow_dispatch:\n" in content
    assert "  schedule:\n" in content
    assert "vars.ENABLE_SCHEMA_SYNC == 'true'" in content
    assert "concurrency:\n  group: schema-sync" in content
    assert 'branch="automation/schema-sync-' in content
    assert 'git push origin "HEAD:$branch"' in content
    assert "git push origin main" not in content
    assert "gh pr create \\\n            --draft" in content


def test_schema_sync_has_write_allowlist_and_always_cleans_up() -> None:
    content = WORKFLOW.read_text(encoding="utf-8")

    assert "secrets.METADATA_BOT_TOKEN || github.token" in content
    assert "Schema sync changed files outside its allowlist" in content
    assert "git add 'catalog/*/generated/raw' 'catalog/*/review'" in content
    assert "if: failure()\n        run: make db-logs" in content
    assert "if: always()\n        run: make db-down" in content
    assert "pull_request_target" not in content
