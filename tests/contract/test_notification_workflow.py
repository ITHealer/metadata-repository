"""Security and routing contract for centralized failure notifications."""

from pathlib import Path

WORKFLOW = Path(".github/workflows/notify-failure.yml")


def test_failure_notifier_monitors_only_explicit_metadata_workflows() -> None:
    content = WORKFLOW.read_text(encoding="utf-8")

    assert content.startswith("name: Metadata Failure Notification\n")
    assert "workflow_run:" in content
    assert "types: [completed]" in content
    for workflow in (
        "Scheduled Schema Sync",
        "Schema Sync UAT",
        "Metadata PR",
        "Index Manifest",
        "Quality",
        "Live LLM UAT",
    ):
        assert f"      - {workflow}" in content
    assert "      - Metadata Failure Notification" not in content
    assert "github.event.workflow_run.conclusion == 'failure'" in content
    assert "github.event.workflow_run.conclusion == 'timed_out'" in content
    assert "github.event.workflow_run.conclusion == 'cancelled'" in content


def test_failure_notifier_never_executes_untrusted_run_content() -> None:
    content = WORKFLOW.read_text(encoding="utf-8")

    assert "actions: read" in content
    assert "contents: read" in content
    assert "contents: write" not in content
    assert "pull-requests: write" not in content
    assert "pull_request_target" not in content
    assert "ref: main" in content
    assert "persist-credentials: false" in content
    assert (
        "head_sha"
        not in content.split("uses: actions/checkout@v4", 1)[1].split(
            "- uses: actions/setup-python@v5", 1
        )[0]
    )
    assert "actions/download-artifact" not in content
    assert "cache:" not in content


def test_failure_event_uses_api_job_data_and_validated_cli() -> None:
    content = WORKFLOW.read_text(encoding="utf-8")

    assert "/actions/runs/${RUN_ID}/jobs" in content
    assert "build/notifications/failed-jobs.txt" in content
    assert "build-job-failed-notification" in content
    assert "./scripts/metadata notify" in content
    assert "TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}" in content
