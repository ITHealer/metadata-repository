"""Map published Git changes and reconcile approved chunks into a full manifest."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from metadata_pipeline.application.classify_changes import ChangedPath
from metadata_pipeline.domain.index import (
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
    current = _manifest_from_chunks(chunks, source_commit)
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
        changed=changed,
    )


def _manifest_from_chunks(chunks: tuple[Chunk, ...], source_commit: str) -> IndexManifest:
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
    return IndexManifest(source_commit=source_commit, documents=tuple(documents))


def _action(action_type: IndexActionType, source_path: str) -> IndexAction | None:
    path = PurePosixPath(source_path)
    parts = path.parts
    if len(parts) != 4 or parts[:2] != ("knowledge", "published") or path.suffix != ".md":
        return None
    return IndexAction(
        action=action_type,
        document_id=f"{parts[2]}.{path.stem}",
        source_path=source_path,
    )
