"""Tests for deterministic reviewer YAML serialization."""

from __future__ import annotations

from pathlib import Path

from metadata_pipeline.io.review_yaml import (
    dump_review_document,
    load_review_document,
    write_review_document,
)


def test_review_yaml_round_trips_and_skips_unchanged_write(tmp_path: Path) -> None:
    review = load_review_document(Path("tests/fixtures/commerce_demo/review/orders.yml"))
    output = tmp_path / "orders.yml"

    assert write_review_document(output, review) is True
    first_bytes = output.read_bytes()
    assert write_review_document(output, review) is False

    assert output.read_bytes() == first_bytes
    assert load_review_document(output) == review
    assert not tuple(tmp_path.glob("*.tmp"))


def test_dump_uses_stable_field_order_and_indented_lists() -> None:
    review = load_review_document(Path("tests/fixtures/commerce_demo/review/customers.yml"))

    content = dump_review_document(review)

    assert content.startswith("contract_version: reviewer-v1\n")
    assert "purpose:\n    - Support customer-level analysis" in content
    assert content.endswith("\n")
