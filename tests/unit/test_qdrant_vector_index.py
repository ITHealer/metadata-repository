"""Adapter contract against Qdrant's in-memory engine."""

from qdrant_client import QdrantClient

from metadata_pipeline.adapters.index.qdrant import QdrantVectorIndex, point_id_for_chunk
from metadata_pipeline.application.bootstrap_vector_index import bootstrap_vector_index
from metadata_pipeline.io.index_settings import IndexSettings
from metadata_pipeline.ports.vector_index import VectorPoint


def test_qdrant_bootstrap_apply_scroll_search_and_delete() -> None:
    settings = IndexSettings(
        enabled=True,
        embedding_model="test-model",
        embedding_dimension=3,
        qdrant_collection="metadata__test_model__3",
    )
    index = QdrantVectorIndex(settings.qdrant_collection, QdrantClient(location=":memory:"))
    bootstrap_vector_index(settings, index)
    point = VectorPoint(
        point_id=point_id_for_chunk("db.table::table_overview::summary"),
        chunk_id="db.table::table_overview::summary",
        body_hash="a" * 64,
        vector=(1.0, 0.0, 0.0),
        payload={
            "managed_by": "metadata-pipeline",
            "chunk_id": "db.table::table_overview::summary",
            "body_hash": "a" * 64,
            "document_id": "db.table",
            "content": "db.table overview",
        },
    )

    index.upsert((point,))
    assert index.list_chunk_states()[0].body_hash == "a" * 64
    assert index.search((1.0, 0.0, 0.0), 1)[0].chunk_id == point.chunk_id
    index.delete((point.point_id,))
    assert not index.list_chunk_states()
