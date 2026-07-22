"""Tests for Git index actions and versioned manifest reconciliation."""

from pathlib import Path

import pytest

from metadata_pipeline.adapters.index.manifest import ManifestIndexStore
from metadata_pipeline.application.classify_changes import ChangedPath
from metadata_pipeline.application.index_changes import (
    diff_manifest_chunks,
    map_index_actions,
    reconcile_index,
)
from metadata_pipeline.domain.index import ChunkActionReason, ChunkActionType, IndexActionType
from metadata_pipeline.domain.published import Chunk
from metadata_pipeline.domain.review import DocumentStatus
from metadata_pipeline.ports.index_store import IndexStoreError


def test_maps_add_modify_delete_and_rename_to_document_actions() -> None:
    actions = map_index_actions(
        (
            ChangedPath("A", "catalog/commerce_demo/generated/published/customers.md"),
            ChangedPath("M", "catalog/commerce_demo/generated/published/orders.md"),
            ChangedPath("D", "catalog/commerce_demo/generated/published/legacy.md"),
            ChangedPath(
                "R100",
                "catalog/commerce_demo/generated/published/order_lines.md",
                "catalog/commerce_demo/generated/published/order_items.md",
            ),
            ChangedPath("M", "README.md"),
        )
    )

    pairs = {(action.action, action.document_id) for action in actions}
    assert pairs == {
        (IndexActionType.UPSERT, "commerce_demo.customers"),
        (IndexActionType.UPSERT, "commerce_demo.orders"),
        (IndexActionType.DELETE, "commerce_demo.legacy"),
        (IndexActionType.DELETE, "commerce_demo.order_items"),
        (IndexActionType.UPSERT, "commerce_demo.order_lines"),
    }


def test_reconcile_is_idempotent_and_excludes_unapproved_chunks(
    tmp_path: Path,
    approved_chunks: tuple[Chunk, ...],
) -> None:
    store = ManifestIndexStore(tmp_path / "manifest.json")
    unapproved = Chunk.model_validate(
        approved_chunks[0]
        .model_copy(
            update={
                "document_status": DocumentStatus.NEEDS_REVIEW,
                "index_eligible": False,
                "table": "preview",
                "qualified_name": "commerce_demo.preview",
                "parent_document_id": "commerce_demo.preview::document",
                "chunk_id": "commerce_demo.preview::column_group::created-at",
            }
        )
        .model_dump()
    )

    first = reconcile_index(store, approved_chunks + (unapproved,), "1" * 40)
    second = reconcile_index(store, approved_chunks + (unapproved,), "1" * 40)

    assert first.changed is True
    assert first.manifest.format_version == "manifest-v2"
    assert len(first.manifest.manifest_hash) == 64
    assert len(first.manifest.documents) == 3
    assert len(first.upserted_chunk_ids) == len(approved_chunks)
    assert not first.deleted_chunk_ids
    assert second.changed is False
    assert not second.deleted_chunk_ids
    assert not second.upserted_chunk_ids
    assert {action.operation for action in second.chunk_actions} == {ChunkActionType.SKIP}
    assert "commerce_demo.preview" not in {
        document.document_id for document in first.manifest.documents
    }


def test_version_change_deletes_old_chunks_before_upserting_replacement(
    tmp_path: Path,
    approved_chunks: tuple[Chunk, ...],
) -> None:
    store = ManifestIndexStore(tmp_path / "manifest.json")
    reconcile_index(store, approved_chunks, "1" * 40)
    changed_orders = tuple(
        Chunk.model_validate(
            chunk.model_copy(update={"source_review_commit": "f" * 40}).model_dump()
        )
        if chunk.qualified_name == "commerce_demo.orders"
        else chunk
        for chunk in approved_chunks
    )

    update = reconcile_index(store, changed_orders, "2" * 40)
    order_ids = {
        chunk.chunk_id
        for chunk in approved_chunks
        if chunk.qualified_name == "commerce_demo.orders"
    }

    assert set(update.deleted_chunk_ids) == order_ids
    assert set(update.upserted_chunk_ids) == order_ids
    orders = next(
        document
        for document in update.manifest.documents
        if document.document_id == "commerce_demo.orders"
    )
    assert orders.source_review_commit == "f" * 40


def test_removed_document_deletes_all_stale_chunks(
    tmp_path: Path,
    approved_chunks: tuple[Chunk, ...],
) -> None:
    store = ManifestIndexStore(tmp_path / "manifest.json")
    reconcile_index(store, approved_chunks, "1" * 40)
    remaining = tuple(
        chunk for chunk in approved_chunks if chunk.qualified_name != "commerce_demo.customers"
    )

    update = reconcile_index(store, remaining, "2" * 40)

    assert update.deleted_chunk_ids
    assert all(
        chunk_id.startswith("commerce_demo.customers::") for chunk_id in update.deleted_chunk_ids
    )
    assert "commerce_demo.customers" not in {
        document.document_id for document in update.manifest.documents
    }


def test_manifest_store_rejects_invalid_existing_json(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(IndexStoreError, match="invalid index manifest"):
        ManifestIndexStore(path).load()


def test_chunk_diff_reports_created_updated_removed_and_unchanged(
    approved_chunks: tuple[Chunk, ...],
) -> None:
    from metadata_pipeline.application.index_changes import build_index_manifest

    previous = build_index_manifest(approved_chunks[:3], "1" * 40)
    updated = approved_chunks[1].model_copy(update={"body_hash": "f" * 64})
    desired = build_index_manifest((updated, approved_chunks[2], approved_chunks[3]), "2" * 40)

    actions = diff_manifest_chunks(previous, desired)
    reasons = {action.reason for action in actions}

    assert reasons == {
        ChunkActionReason.CREATED,
        ChunkActionReason.REMOVED,
        ChunkActionReason.UNCHANGED,
        ChunkActionReason.UPDATED,
    }
