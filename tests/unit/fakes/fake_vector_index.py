"""In-memory vector index test double with operation tracing."""

from __future__ import annotations

from dataclasses import dataclass, field

from metadata_pipeline.ports.vector_index import (
    VectorChunkState,
    VectorCollectionInfo,
    VectorIndexError,
    VectorPoint,
    VectorSearchHit,
)


@dataclass
class FakeVectorIndex:
    dimension: int
    exists: bool = True
    points: dict[str, VectorPoint] = field(default_factory=dict)
    operations: list[str] = field(default_factory=list)
    fail_upsert_after: int | None = None

    def point_id_for_chunk(self, chunk_id: str) -> str:
        return f"point:{chunk_id}"

    def collection_info(self) -> VectorCollectionInfo | None:
        if not self.exists:
            return None
        return VectorCollectionInfo(dimension=self.dimension, distance="cosine")

    def create_collection(self, dimension: int, distance: str) -> None:
        self.operations.append(f"create:{dimension}:{distance}")
        self.dimension = dimension
        self.exists = True

    def list_chunk_states(self) -> tuple[VectorChunkState, ...]:
        return tuple(
            sorted(
                (
                    VectorChunkState(
                        point_id=point.point_id,
                        chunk_id=point.chunk_id,
                        body_hash=point.body_hash,
                    )
                    for point in self.points.values()
                ),
                key=lambda item: item.chunk_id,
            )
        )

    def upsert(self, points: tuple[VectorPoint, ...]) -> None:
        self.operations.append(f"upsert:{len(points)}")
        for index, point in enumerate(points):
            if self.fail_upsert_after is not None and index >= self.fail_upsert_after:
                self.fail_upsert_after = None
                raise VectorIndexError("simulated partial upsert")
            self.points[point.point_id] = point

    def delete(self, point_ids: tuple[str, ...]) -> None:
        self.operations.append(f"delete:{len(point_ids)}")
        for point_id in point_ids:
            self.points.pop(point_id, None)

    def search(self, vector: tuple[float, ...], limit: int) -> tuple[VectorSearchHit, ...]:
        hits = sorted(
            self.points.values(),
            key=lambda point: -sum(a * b for a, b in zip(vector, point.vector)),
        )[:limit]
        return tuple(
            VectorSearchHit(
                chunk_id=point.chunk_id,
                document_id=str(point.payload["document_id"]),
                content=str(point.payload["content"]),
                score=float(sum(a * b for a, b in zip(vector, point.vector))),
            )
            for point in hits
        )
