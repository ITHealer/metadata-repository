"""Qdrant adapter restricted to the metadata pipeline managed namespace."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from qdrant_client import QdrantClient, models

from metadata_pipeline.io.index_settings import IndexSettings
from metadata_pipeline.ports.vector_index import (
    VectorChunkState,
    VectorCollectionInfo,
    VectorIndexError,
    VectorPoint,
    VectorSearchHit,
)

_POINT_NAMESPACE = uuid.UUID("5ac73d9e-2ed0-5afd-b7ba-6650a6c90298")
_MANAGED_BY = "metadata-pipeline"
_MUTATION_BATCH_SIZE = 128


def point_id_for_chunk(chunk_id: str) -> str:
    """Map a stable chunk ID to an accepted deterministic Qdrant UUID."""
    return str(uuid.uuid5(_POINT_NAMESPACE, chunk_id))


@dataclass(frozen=True)
class QdrantVectorIndex:
    """Apply and retrieve metadata points from one configured collection."""

    collection: str
    client: Any

    @classmethod
    def from_settings(cls, settings: IndexSettings) -> QdrantVectorIndex:
        client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
            timeout=max(1, int(settings.timeout_seconds)),
        )
        return cls(collection=settings.qdrant_collection, client=client)

    def point_id_for_chunk(self, chunk_id: str) -> str:
        return point_id_for_chunk(chunk_id)

    def collection_info(self) -> VectorCollectionInfo | None:
        try:
            if not self.client.collection_exists(self.collection):
                return None
            info = self.client.get_collection(self.collection)
            vectors = info.config.params.vectors
            if isinstance(vectors, dict):
                raise VectorIndexError("named-vector collections are not supported")
            return VectorCollectionInfo(
                dimension=int(vectors.size),
                distance=str(vectors.distance.value).lower(),
            )
        except VectorIndexError:
            raise
        except Exception as error:
            raise VectorIndexError("unable to read Qdrant collection configuration") from error

    def create_collection(self, dimension: int, distance: str) -> None:
        if distance.lower() != "cosine":
            raise VectorIndexError("Qdrant adapter supports only cosine distance")
        try:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=models.VectorParams(
                    size=dimension,
                    distance=models.Distance.COSINE,
                ),
            )
        except Exception as error:
            raise VectorIndexError("unable to create Qdrant collection") from error

    def list_chunk_states(self) -> tuple[VectorChunkState, ...]:
        states: list[VectorChunkState] = []
        offset: Any = None
        try:
            while True:
                points, offset = self.client.scroll(
                    collection_name=self.collection,
                    scroll_filter=_managed_filter(),
                    limit=256,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                for point in points:
                    payload = point.payload or {}
                    states.append(
                        VectorChunkState(
                            point_id=str(point.id),
                            chunk_id=str(payload["chunk_id"]),
                            body_hash=str(payload["body_hash"]),
                        )
                    )
                if offset is None:
                    break
        except (KeyError, ValueError) as error:
            raise VectorIndexError("Qdrant managed point payload is invalid") from error
        except Exception as error:
            raise VectorIndexError("unable to list Qdrant managed points") from error
        return tuple(sorted(states, key=lambda item: item.chunk_id))

    def upsert(self, points: tuple[VectorPoint, ...]) -> None:
        if not points:
            return
        try:
            for start in range(0, len(points), _MUTATION_BATCH_SIZE):
                batch = points[start : start + _MUTATION_BATCH_SIZE]
                self.client.upsert(
                    collection_name=self.collection,
                    points=[
                        models.PointStruct(
                            id=point.point_id,
                            vector=list(point.vector),
                            payload=point.payload,
                        )
                        for point in batch
                    ],
                    wait=True,
                )
        except Exception as error:
            raise VectorIndexError("unable to upsert Qdrant points") from error

    def delete(self, point_ids: tuple[str, ...]) -> None:
        if not point_ids:
            return
        try:
            for start in range(0, len(point_ids), _MUTATION_BATCH_SIZE):
                self.client.delete(
                    collection_name=self.collection,
                    points_selector=list(point_ids[start : start + _MUTATION_BATCH_SIZE]),
                    wait=True,
                )
        except Exception as error:
            raise VectorIndexError("unable to delete Qdrant points") from error

    def search(self, vector: tuple[float, ...], limit: int) -> tuple[VectorSearchHit, ...]:
        try:
            response = self.client.query_points(
                collection_name=self.collection,
                query=list(vector),
                query_filter=_managed_filter(),
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
            hits = []
            for point in response.points:
                payload = point.payload or {}
                hits.append(
                    VectorSearchHit(
                        chunk_id=str(payload["chunk_id"]),
                        document_id=str(payload["document_id"]),
                        content=str(payload["content"]),
                        score=float(point.score),
                    )
                )
            return tuple(hits)
        except (KeyError, ValueError) as error:
            raise VectorIndexError("Qdrant search payload is invalid") from error
        except Exception as error:
            raise VectorIndexError("unable to query Qdrant collection") from error


def _managed_filter() -> models.Filter:
    return models.Filter(
        must=[
            models.FieldCondition(
                key="managed_by",
                match=models.MatchValue(value=_MANAGED_BY),
            )
        ]
    )
