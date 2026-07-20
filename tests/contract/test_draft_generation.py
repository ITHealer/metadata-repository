"""Golden contract tests for deterministic drafts from the committed tbls schema."""

from __future__ import annotations

from pathlib import Path

from metadata_pipeline.application.create_drafts import DraftAction, create_review_drafts
from metadata_pipeline.application.review_contract import validate_review_directory
from metadata_pipeline.validation.review import IssueSeverity

SCHEMA_PATH = Path("catalog/commerce_demo/generated/raw/schema.json")
CONTRACT_PATH = Path("contracts/metadata_contract.yml")
GOLDEN_DIR = Path("tests/golden/review/commerce_demo")


def test_three_demo_drafts_match_golden_and_are_idempotent(tmp_path: Path) -> None:
    review_dir = tmp_path / "review"

    created = create_review_drafts(SCHEMA_PATH, review_dir, CONTRACT_PATH)
    unchanged = create_review_drafts(SCHEMA_PATH, review_dir, CONTRACT_PATH)

    assert {result.action for result in created} == {DraftAction.CREATED}
    assert {result.action for result in unchanged} == {DraftAction.UNCHANGED}
    for golden_path in sorted(GOLDEN_DIR.glob("*.yml")):
        generated_path = review_dir / golden_path.name
        assert generated_path.read_text(encoding="utf-8") == golden_path.read_text(encoding="utf-8")

    issues = validate_review_directory(SCHEMA_PATH, review_dir, CONTRACT_PATH)
    assert issues
    assert all(issue.severity is IssueSeverity.WARNING for issue in issues)
