"""Filesystem contract tests for preflight, publish, validation, and chunk dry-run."""

from pathlib import Path
from shutil import copy2

import pytest
import yaml

from metadata_pipeline.adapters.generator.deterministic import DeterministicDocumentGenerator
from metadata_pipeline.application.publish_metadata import (
    PublicationPreflightError,
    prepare_chunk_artifact,
    prepare_publication,
    publish_batch,
    validate_published_directory,
    write_chunk_artifact,
)

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "schema/raw/commerce_demo/schema.json"
CONTRACT = ROOT / "contracts/metadata_contract.yml"
REVIEWS = ROOT / "metadata/review/commerce_demo"
COMMIT = "b" * 40


def _copy_reviews(target: Path) -> None:
    target.mkdir(parents=True)
    for source in REVIEWS.glob("*.yml"):
        copy2(source, target / source.name)


def test_publish_all_documents_is_idempotent_and_chunkable(tmp_path: Path) -> None:
    review_dir = tmp_path / "review"
    output_dir = tmp_path / "published"
    _copy_reviews(review_dir)
    batch = prepare_publication(
        SCHEMA,
        review_dir,
        CONTRACT,
        output_dir,
        COMMIT,
        DeterministicDocumentGenerator(),
    )
    assert len(batch.items) == 3
    assert not output_dir.exists()
    assert {result.action.value for result in publish_batch(batch, output_dir)} == {"created"}
    assert {result.action.value for result in publish_batch(batch, output_dir)} == {"unchanged"}
    assert not validate_published_directory(batch, output_dir)

    chunks = prepare_chunk_artifact(batch, tmp_path / "chunks.jsonl")
    assert chunks
    assert all(chunk.index_eligible is False for chunk in chunks)
    assert write_chunk_artifact(tmp_path / "chunks.jsonl", chunks) is True
    assert write_chunk_artifact(tmp_path / "chunks.jsonl", chunks) is False


def test_stale_review_fails_before_any_published_write(tmp_path: Path) -> None:
    review_dir = tmp_path / "review"
    output_dir = tmp_path / "published"
    _copy_reviews(review_dir)
    orders_path = review_dir / "orders.yml"
    payload = yaml.safe_load(orders_path.read_text(encoding="utf-8"))
    payload["schema_hash"] = "0" * 64
    orders_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(PublicationPreflightError) as captured:
        prepare_publication(
            SCHEMA,
            review_dir,
            CONTRACT,
            output_dir,
            COMMIT,
            DeterministicDocumentGenerator(),
        )
    assert "stale_schema_hash" in {issue.code for issue in captured.value.issues}
    assert not output_dir.exists()


def test_conflicting_evidence_blocks_needs_review_preview(tmp_path: Path) -> None:
    review_dir = tmp_path / "review"
    _copy_reviews(review_dir)
    orders_path = review_dir / "orders.yml"
    payload = yaml.safe_load(orders_path.read_text(encoding="utf-8"))
    payload["business"]["evidence"][0]["status"] = "conflicting"
    orders_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(PublicationPreflightError) as captured:
        prepare_publication(
            SCHEMA,
            review_dir,
            CONTRACT,
            tmp_path / "published",
            COMMIT,
            DeterministicDocumentGenerator(),
        )
    assert "conflicting_evidence" in {issue.code for issue in captured.value.issues}


def test_published_validation_detects_manual_edit_and_orphan(tmp_path: Path) -> None:
    review_dir = tmp_path / "review"
    output_dir = tmp_path / "published"
    _copy_reviews(review_dir)
    batch = prepare_publication(
        SCHEMA,
        review_dir,
        CONTRACT,
        output_dir,
        COMMIT,
        DeterministicDocumentGenerator(),
    )
    publish_batch(batch, output_dir)
    orders_path = output_dir / "orders.md"
    orders_path.write_text(orders_path.read_text(encoding="utf-8") + "manual edit\n")
    (output_dir / "orphan.md").write_text("orphan\n", encoding="utf-8")
    codes = {issue.code for issue in validate_published_directory(batch, output_dir)}
    assert codes == {"stale_published_document", "orphaned_published_document"}
