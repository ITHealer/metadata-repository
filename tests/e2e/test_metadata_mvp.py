"""Full-pipeline UAT scenarios that require no external secret or service."""

import json
from pathlib import Path
from shutil import copy2
from typing import Any

import pytest
import yaml

from metadata_pipeline.adapters.generator.deterministic import DeterministicDocumentGenerator
from metadata_pipeline.adapters.index.manifest import ManifestIndexStore
from metadata_pipeline.application.create_drafts import DraftAction, create_review_drafts
from metadata_pipeline.application.index_changes import reconcile_index
from metadata_pipeline.application.publish_metadata import (
    PublicationPreflightError,
    prepare_publication,
)
from metadata_pipeline.application.retrieval_evaluation import (
    evaluate_retrieval,
    load_golden_questions,
)
from metadata_pipeline.domain.published import Chunk
from metadata_pipeline.io.review_yaml import load_review_document

SCHEMA = Path("catalog/commerce_demo/generated/raw/schema.json")
REVIEWS = Path("catalog/commerce_demo/review")
CONTRACT = Path("contracts/metadata_contract.yml")
QUESTIONS = Path("tests/fixtures/golden_questions.yml")


@pytest.mark.e2e
def test_happy_path_approved_chunks_reach_manifest_and_retrieval(
    tmp_path: Path,
    approved_chunks: tuple[Chunk, ...],
) -> None:
    update = reconcile_index(
        ManifestIndexStore(tmp_path / "manifest.json"),
        approved_chunks,
        "1" * 40,
    )
    report = evaluate_retrieval(approved_chunks, load_golden_questions(QUESTIONS))

    assert len(update.manifest.documents) == 3
    assert report.document_hit_rate == 1.0
    assert report.passed is True


@pytest.mark.e2e
def test_schema_change_creates_table_and_refreshes_affected_review(tmp_path: Path) -> None:
    review_dir = tmp_path / "review"
    review_dir.mkdir()
    for source in REVIEWS.glob("*.yml"):
        copy2(source, review_dir / source.name)
    payload: dict[str, Any] = json.loads(SCHEMA.read_text(encoding="utf-8"))
    orders = next(table for table in payload["tables"] if table["name"] == "orders")
    orders["columns"].append(
        {
            "name": "channel",
            "type": "LowCardinality(String)",
            "nullable": False,
            "comment": "Order acquisition channel: web, mobile, or partner",
        }
    )
    payload["tables"].append(
        {
            "name": "order_events",
            "type": "BASE TABLE",
            "comment": "Synthetic order lifecycle events.",
            "columns": [
                {
                    "name": "event_id",
                    "type": "UUID",
                    "nullable": False,
                    "comment": "Stable event identifier",
                },
                {
                    "name": "order_id",
                    "type": "UUID",
                    "nullable": False,
                    "comment": "Associated order identifier",
                },
            ],
        }
    )
    changed_schema = tmp_path / "schema.json"
    changed_schema.write_text(json.dumps(payload), encoding="utf-8")

    results = create_review_drafts(changed_schema, review_dir, CONTRACT)

    assert next(result for result in results if result.table == "orders").action is (
        DraftAction.REFRESHED
    )
    assert next(result for result in results if result.table == "order_events").action is (
        DraftAction.CREATED
    )
    assert "channel" in load_review_document(review_dir / "orders.yml").columns


@pytest.mark.e2e
def test_invalid_column_is_blocked_before_any_published_output(tmp_path: Path) -> None:
    review_dir = tmp_path / "review"
    review_dir.mkdir()
    for source in REVIEWS.glob("*.yml"):
        copy2(source, review_dir / source.name)
    orders_path = review_dir / "orders.yml"
    payload = yaml.safe_load(orders_path.read_text(encoding="utf-8"))
    payload["columns"]["not_a_real_column"] = payload["columns"]["order_id"]
    orders_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    output_dir = tmp_path / "published"

    with pytest.raises(PublicationPreflightError) as captured:
        prepare_publication(
            SCHEMA,
            review_dir,
            CONTRACT,
            output_dir,
            "2" * 40,
            DeterministicDocumentGenerator(),
        )

    assert "unknown_column" in {issue.code for issue in captured.value.issues}
    assert not output_dir.exists()
