"""Safety contracts for production schema sync and disposable fixture UAT."""

from pathlib import Path

PRODUCTION = Path(".github/workflows/schema-sync.yml")
UAT = Path(".github/workflows/schema-sync-uat.yml")
RUNTIME = Path("src/metadata_pipeline/adapters/github/schema_sync_runtime.py")


def test_production_schema_sync_is_daily_remote_and_preflight_first() -> None:
    content = PRODUCTION.read_text(encoding="utf-8")

    assert content.startswith("name: Scheduled Schema Sync\n")
    assert 'cron: "17 18 * * *"' in content
    assert "runs-on: [self-hosted, schema-sync]" in content
    assert "Resolve the single active schema-sync PR" in content
    assert "schema-sync-pr-prepare" in content
    assert "make scheduled-sync" in content
    assert "schema-sync-pr-publish" in content
    assert "make db-up" not in content
    assert "apply_schema_sync_fixture.sh" not in content
    assert "make schema-doc" not in content


def test_production_has_two_layer_gate_runner_contract_and_direct_secret_mapping() -> None:
    content = PRODUCTION.read_text(encoding="utf-8")

    gate = (
        "vars.SCHEMA_SYNC_ENABLED == 'true' || "
        "(github.event_name == 'workflow_dispatch' && inputs.force_run)"
    )
    assert content.count(gate) == 2
    assert "force_run:" in content
    assert "SCHEMA_SYNC_ENABLED:" in content
    assert "TBLS_DSN_URCARD: ${{ secrets.TBLS_DSN_URCARD }}" in content
    assert "for tool in git gh docker python3" in content
    assert "docker compose version" in content
    assert "METADATA_BOT_TOKEN is required" in content
    assert ".env" not in content


def test_single_active_pr_runtime_never_force_pushes_or_changes_ready_state() -> None:
    workflow = PRODUCTION.read_text(encoding="utf-8")
    runtime = RUNTIME.read_text(encoding="utf-8")

    assert "concurrency:\n  group: schema-sync\n  cancel-in-progress: false" in workflow
    assert '"--label",\n                label' in runtime
    assert 'self._run(("git", "push", "origin", f"HEAD:{branch}"))' in runtime
    assert "--force" not in runtime
    assert "rebase" not in runtime
    assert "--ready" not in runtime
    assert "git push origin main" not in workflow
    assert "gh pr merge" not in workflow


def test_fixture_uat_remains_manual_and_always_cleans_up_clickhouse() -> None:
    content = UAT.read_text(encoding="utf-8")

    assert content.startswith("name: Schema Sync UAT\n")
    assert "  workflow_dispatch:\n" in content
    assert "  schedule:\n" not in content
    assert "scenario:" in content
    assert "make db-up" in content
    assert "apply_schema_sync_fixture.sh" in content
    assert "Assert selected UAT schema scenario" in content
    assert "inputs.scenario" in content
    assert "grep --fixed-strings --quiet" in content
    assert '"name": "channel"' in content
    assert "git status --porcelain=v1 --untracked-files=all -- catalog" in content
    assert "if: failure()\n        run: make db-logs" in content
    assert "if: always()\n        run: make db-down" in content


def test_schema_sync_inputs_continue_to_trigger_the_metadata_pr_generate_loop() -> None:
    content = Path(".github/workflows/metadata-pr.yml").read_text(encoding="utf-8")

    assert "steps.changes.outputs.pr_has_inputs" in content
    assert "mode=generate" in content
    assert "steps.changes.outputs.latest_only_published" in content
    assert "mode=validate" in content
    assert 'git push origin "HEAD:$HEAD_BRANCH"' in content
