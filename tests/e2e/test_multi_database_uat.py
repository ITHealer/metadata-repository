"""Network-free UAT proving database isolation and approved candidate chunking."""

from __future__ import annotations

import json
from pathlib import Path
from shutil import copy2
from typing import Any

import pytest

from metadata_pipeline.adapters.schema.tbls_json import TblsSchemaSource
from metadata_pipeline.cli import main
from metadata_pipeline.domain.hashing import table_schema_hash
from metadata_pipeline.domain.review import DocumentStatus, Evidence, EvidenceStatus, ReviewDocument
from metadata_pipeline.io.candidate_json import load_candidate
from metadata_pipeline.io.chunk_jsonl import load_chunks
from metadata_pipeline.io.review_yaml import load_review_document, write_review_document

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.e2e
def test_two_clickhouse_databases_sync_promote_and_chunk_without_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _build_repository(tmp_path)
    monkeypatch.chdir(tmp_path)

    assert main(["catalog-check-all"]) == 0
    for database in ("urgift", "urcard"):
        assert _sync(database) == 0
        candidate = load_candidate(
            tmp_path / f"catalog/{database}/generated/structured/customers.json"
        )
        assert candidate.state.value == "review"

    for database in ("urgift", "urcard"):
        review_path = tmp_path / f"catalog/{database}/review/customers.yml"
        review = load_review_document(review_path)
        write_review_document(
            review_path,
            review.model_copy(update={"document_status": DocumentStatus.APPROVED}),
        )
        assert _sync(database) == 0

    output = tmp_path / "build/chunks/catalog.jsonl"
    assert main(["chunk-catalog", "--output", str(output)]) == 0
    chunks = load_chunks(output)

    assert {chunk.database for chunk in chunks} == {"UrGift", "UrCard"}
    assert {chunk.table for chunk in chunks} == {"customers"}
    assert len({chunk.chunk_id for chunk in chunks}) == len(chunks)
    assert all(chunk.index_eligible for chunk in chunks)
    assert "2 document(s)" in capsys.readouterr().out


def _sync(database: str) -> int:
    return main(
        [
            "sync-candidates",
            "--database",
            database,
            "--source-review-commit",
            "a" * 40,
            "--mode",
            "mock",
        ]
    )


def _build_repository(root: Path) -> None:
    (root / "contracts").mkdir()
    (root / "guidelines").mkdir()
    copy2(ROOT / "contracts/metadata_contract.yml", root / "contracts/metadata_contract.yml")
    copy2(
        ROOT / "guidelines/llm_transformation_guideline.md",
        root / "guidelines/llm_transformation_guideline.md",
    )
    source_payload: dict[str, Any] = json.loads(
        (ROOT / "catalog/commerce_demo/generated/raw/schema.json").read_text(encoding="utf-8")
    )
    customer_table = next(
        table for table in source_payload["tables"] if table["name"] == "customers"
    )
    source_review = load_review_document(ROOT / "catalog/commerce_demo/review/customers.yml")
    for key, clickhouse_name in (("urgift", "UrGift"), ("urcard", "UrCard")):
        profile_dir = root / f"config/databases/{key}"
        profile_dir.mkdir(parents=True)
        profile_dir.joinpath("database.yml").write_text(
            f"enabled: true\nkey: {key}\ndisplay_name: {clickhouse_name}\n"
            f"clickhouse_database: {clickhouse_name}\n"
            "description: Ephemeral multi-database UAT fixture.\ntables: [customers]\n",
            encoding="utf-8",
        )
        profile_dir.joinpath("tbls.yml").write_text(
            f"name: {clickhouse_name}\ninclude: [customers]\n",
            encoding="utf-8",
        )
        raw_dir = root / f"catalog/{key}/generated/raw"
        raw_dir.mkdir(parents=True)
        schema_path = raw_dir / "schema.json"
        schema_path.write_text(
            json.dumps(
                {
                    "name": clickhouse_name,
                    "desc": "Ephemeral UAT schema; not a production schema.",
                    "tables": [customer_table],
                    "relations": [],
                }
            ),
            encoding="utf-8",
        )
        schema = TblsSchemaSource(schema_path).load()
        review_dir = root / f"catalog/{key}/review"
        review_dir.mkdir(parents=True)
        review = _ready_review(source_review, key, clickhouse_name)
        review = review.model_copy(
            update={"schema_hash": table_schema_hash(schema, schema.tables[0])}
        )
        write_review_document(review_dir / "customers.yml", review)


def _ready_review(source: ReviewDocument, key: str, database: str) -> ReviewDocument:
    payload = json.loads(
        json.dumps(source.model_dump(mode="json")).replace(
            "catalog/commerce_demo/", f"catalog/{key}/"
        )
    )
    review = ReviewDocument.model_validate(payload)
    return review.model_copy(
        update={
            "database": database,
            "owner": f"{key}-owner",
            "reviewer": "uat-reviewer",
            "business": review.business.model_copy(
                update={"evidence": _confirmed(review.business.evidence)}
            ),
            "columns": {
                name: column.model_copy(update={"evidence": _confirmed(column.evidence)})
                for name, column in review.columns.items()
            },
        }
    )


def _confirmed(evidence: tuple[Evidence, ...]) -> tuple[Evidence, ...]:
    return tuple(item.model_copy(update={"status": EvidenceStatus.CONFIRMED}) for item in evidence)
