"""Map published Git changes and reconcile approved chunks into a full manifest."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from metadata_pipeline.application.classify_changes import ChangedPath
from metadata_pipeline.domain.index import (
    ChunkAction,
    ChunkActionReason,
    ChunkActionType,
    IndexAction,
    IndexActionType,
    IndexedDocument,
    IndexManifest,
)
from metadata_pipeline.domain.published import Chunk
from metadata_pipeline.ports.index_store import IndexStore


@dataclass(frozen=True)
class IndexUpdate:
    """Observable delete-before-upsert result for one manifest reconciliation."""

    manifest: IndexManifest
    deleted_chunk_ids: tuple[str, ...]
    upserted_chunk_ids: tuple[str, ...]
    chunk_actions: tuple[ChunkAction, ...]
    changed: bool


def map_index_actions(changes: tuple[ChangedPath, ...]) -> tuple[IndexAction, ...]:
    """Map Git A/M/D/R/C statuses under published output to document actions."""
    actions: list[IndexAction] = []
    for change in changes:
        status = change.status[:1]
        if status in {"D", "R"} and change.previous_path:
            action = _action(IndexActionType.DELETE, change.previous_path)
            if action is not None:
                actions.append(action)
        elif status == "D":
            action = _action(IndexActionType.DELETE, change.path)
            if action is not None:
                actions.append(action)
        if status in {"A", "M", "R", "C"}:
            action = _action(IndexActionType.UPSERT, change.path)
            if action is not None:
                actions.append(action)
    unique = {(item.action.value, item.document_id, item.source_path): item for item in actions}
    return tuple(unique[key] for key in sorted(unique))


def reconcile_index(
    store: IndexStore,
    chunks: tuple[Chunk, ...],
    source_commit: str,
) -> IndexUpdate:
    """Replace the full approved snapshot and report stale deletes before new upserts."""
    previous = store.load()
    current = build_index_manifest(chunks, source_commit)
    chunk_actions = diff_manifest_chunks(previous, current)
    previous_by_id = {document.document_id: document for document in previous.documents}
    current_by_id = {document.document_id: document for document in current.documents}
    deleted: list[str] = []
    upserted: list[str] = []
    for document_id, old_document in previous_by_id.items():
        if current_by_id.get(document_id) != old_document:
            deleted.extend(chunk.chunk_id for chunk in old_document.chunks)
    for document_id, new_document in current_by_id.items():
        if previous_by_id.get(document_id) != new_document:
            upserted.extend(chunk.chunk_id for chunk in new_document.chunks)
    changed = store.save(current)
    return IndexUpdate(
        manifest=current,
        deleted_chunk_ids=tuple(sorted(deleted)),
        upserted_chunk_ids=tuple(sorted(upserted)),
        chunk_actions=chunk_actions,
        changed=changed,
    )


def build_index_manifest(chunks: tuple[Chunk, ...], source_commit: str) -> IndexManifest:
    """Build one complete approved-only manifest with a stable content hash."""
    grouped: dict[str, list[Chunk]] = {}
    for chunk in chunks:
        if chunk.index_eligible:
            grouped.setdefault(chunk.qualified_name, []).append(chunk)
    documents = []
    for document_id, document_chunks in sorted(grouped.items()):
        ordered = tuple(sorted(document_chunks, key=lambda item: item.chunk_id))
        first = ordered[0]
        documents.append(
            IndexedDocument(
                document_id=document_id,
                schema_hash=first.schema_hash,
                source_review_commit=first.source_review_commit,
                transformation_guideline_version=first.transformation_guideline_version,
                chunks=ordered,
            )
        )
    return IndexManifest.create(source_commit=source_commit, documents=tuple(documents))


def diff_manifest_chunks(
    previous: IndexManifest,
    desired: IndexManifest,
) -> tuple[ChunkAction, ...]:
    """Compare complete manifests by stable chunk ID and body hash."""
    old = _chunks_by_id(previous)
    new = _chunks_by_id(desired)
    actions: list[ChunkAction] = []
    for chunk_id in sorted(old.keys() | new.keys()):
        old_hash = old[chunk_id].body_hash if chunk_id in old else None
        new_hash = new[chunk_id].body_hash if chunk_id in new else None
        if old_hash is None:
            operation = ChunkActionType.UPSERT
            reason = ChunkActionReason.CREATED
        elif new_hash is None:
            operation = ChunkActionType.DELETE
            reason = ChunkActionReason.REMOVED
        elif old_hash != new_hash:
            operation = ChunkActionType.UPSERT
            reason = ChunkActionReason.UPDATED
        else:
            operation = ChunkActionType.SKIP
            reason = ChunkActionReason.UNCHANGED
        actions.append(
            ChunkAction(
                operation=operation,
                reason=reason,
                chunk_id=chunk_id,
                old_hash=old_hash,
                new_hash=new_hash,
            )
        )
    return tuple(actions)


def _chunks_by_id(manifest: IndexManifest) -> dict[str, Chunk]:
    chunks = {chunk.chunk_id: chunk for document in manifest.documents for chunk in document.chunks}
    expected_count = sum(len(document.chunks) for document in manifest.documents)
    if len(chunks) != expected_count:
        raise ValueError("manifest chunk IDs must be globally unique")
    return chunks


def _action(action_type: IndexActionType, source_path: str) -> IndexAction | None:
    path = PurePosixPath(source_path)
    parts = path.parts
    if (
        len(parts) != 5
        or parts[0] != "catalog"
        or parts[2:4] != ("generated", "published")
        or path.suffix != ".md"
    ):
        return None
    return IndexAction(
        action=action_type,
        document_id=f"{parts[1]}.{path.stem}",
        source_path=source_path,
    )
