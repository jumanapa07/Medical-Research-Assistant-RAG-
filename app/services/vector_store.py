import uuid
import numpy as np

from typing import Protocol
from qdrant_client import QdrantClient, models


class VectorStore(Protocol):
    """Common interface for vector database implementations."""

    def upsert(self, chunks: list[dict], embeddings: np.ndarray) -> None: ...

    def delete_document(
        self, tenant_id: str, document_id: str, keep_chunk_ids: set
    ) -> int: ...

    def search(
        self,
        query_vec: np.ndarray,
        tenant_id: str,
        owner_id: str,
        k: int = 5,
    ) -> list[tuple[dict, float]]: ...

    def get_chunks(
        self,
        tenant_id: str,
        owner_id: str,
    ) -> list[dict]: ...
    
    def count(self, tenant_id: str = None, document_id: str = None) -> int: ...


class InMemoryVectorStore:
    """In-memory vector store for local testing."""

    def __init__(self):
        self._rows: dict[str, tuple[dict, np.ndarray]] = {}

    def upsert(self, chunks, embeddings):
        if len(chunks) != len(embeddings):
            raise ValueError("Chunks and embeddings count mismatch")

        for chunk, vector in zip(chunks, embeddings):
            self._rows[chunk["chunk_id"]] = (
                chunk,
                np.asarray(vector, dtype=np.float32),
            )

    def delete_document(self, tenant_id, document_id, keep_chunk_ids):
        stale = [
            chunk_id
            for chunk_id, (chunk, _) in self._rows.items()
            if chunk["tenant_id"] == tenant_id
            and chunk["document_id"] == document_id
            and chunk_id not in keep_chunk_ids
        ]

        for chunk_id in stale:
            del self._rows[chunk_id]

        return len(stale)

    def search(self, query_vec, tenant_id, owner_id, k=5):

        rows = [
            (chunk, vector)
            for chunk, vector in self._rows.values()
            if chunk["tenant_id"] == tenant_id
            and (chunk["owner_id"] == owner_id or chunk["visibility"] == "public")
        ]

        if not rows:
            return []

        scores = np.array([float(vector @ query_vec) for _, vector in rows])

        order = np.argsort(-scores)[:k]

        return [(rows[i][0], float(scores[i])) for i in order]

    def count(self, tenant_id=None, document_id=None):
        return sum(
            1
            for chunk, _ in self._rows.values()
            if (tenant_id is None or chunk["tenant_id"] == tenant_id)
            and (document_id is None or chunk["document_id"] == document_id)
        )

    def get_chunks(self, tenant_id: str, owner_id: str) -> list[dict]:
        return [
            chunk
            for chunk, _ in self._rows.values()
            if chunk["tenant_id"] == tenant_id
            and (
                chunk["owner_id"] == owner_id
                or chunk["visibility"] == "public"
            )
        ]

class QdrantVectorStore:
    """Persistent vector storage using Qdrant."""

    def __init__(
        self,
        collection_name: str,
        vector_size: int,
        url: str = "http://localhost:6333",
        api_key: str = None,
        batch_size: int = 100,
    ):
        self.collection_name = collection_name
        self.vector_size = vector_size
        self.batch_size = batch_size

        self.client = QdrantClient(url=url, api_key=api_key)

        self._initialize_collection()

    def _initialize_collection(self):
        collections = self.client.get_collections().collections

        exists = any(
            collection.name == self.collection_name for collection in collections
        )

        if not exists:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=self.vector_size, distance=models.Distance.COSINE
                ),
            )

        info = self.client.get_collection(self.collection_name)
        vector_config = info.config.params.vectors

        if not isinstance(vector_config, models.VectorParams):
            raise ValueError("Expected a single unnamed vector configuration")

        if vector_config.size != self.vector_size:
            raise ValueError(
                f"Collection dimension mismatch: "
                f"expected {self.vector_size}, got {vector_config.size}"
            )

        # Index fields used for filtering.
        for field in [
            "chunk_id",
            "document_id",
            "tenant_id",
            "owner_id",
            "visibility",
            "version",
        ]:
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name=field,
                field_schema=models.PayloadSchemaType.KEYWORD,
            )

    def upsert(self, chunks, embeddings):
        if len(chunks) != len(embeddings):
            raise ValueError("Chunks and embeddings count mismatch")

        for start in range(0, len(chunks), self.batch_size):
            batch_chunks = chunks[start : start + self.batch_size]
            batch_embeddings = embeddings[start : start + self.batch_size]

            points = []

            for chunk, embedding in zip(batch_chunks, batch_embeddings):
                vector = np.asarray(embedding, dtype=np.float32)

                if vector.shape != (self.vector_size,):
                    raise ValueError("Invalid embedding dimension")

                if not np.isfinite(vector).all():
                    raise ValueError("Embedding contains invalid values")

                point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, chunk["chunk_id"]))

                points.append(
                    models.PointStruct(
                        id=point_id, vector=vector.tolist(), payload=dict(chunk)
                    )
                )

            self.client.upsert(
                collection_name=self.collection_name, points=points, wait=True
            )

    def delete_document(self, tenant_id, document_id, keep_chunk_ids):
        conditions = [
            models.FieldCondition(
                key="tenant_id", match=models.MatchValue(value=tenant_id)
            ),
            models.FieldCondition(
                key="document_id", match=models.MatchValue(value=document_id)
            ),
        ]

        if keep_chunk_ids:
            conditions.append(
                models.Filter(
                    must_not=[
                        models.FieldCondition(
                            key="chunk_id",
                            match=models.MatchAny(any=list(keep_chunk_ids)),
                        )
                    ]
                )
            )

        query_filter = models.Filter(must=conditions)

        count = self.client.count(
            collection_name=self.collection_name, count_filter=query_filter, exact=True
        ).count

        self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(filter=query_filter),
            wait=True,
        )

        return count

    def search(self, query_vec, tenant_id, owner_id, k=5):

        conditions = [
            models.FieldCondition(
                key="tenant_id", match=models.MatchValue(value=tenant_id)
            ),
            models.Filter(
                should=[
                    models.FieldCondition(
                        key="owner_id", match=models.MatchValue(value=owner_id)
                    ),
                    models.FieldCondition(
                        key="visibility", match=models.MatchValue(value="public")
                    ),
                ]
            ),
        ]

        query_filter = models.Filter(must=conditions)

        results = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vec.tolist(),
            query_filter=query_filter,
            limit=k,
            with_payload=True,
        )

        return [(point.payload, float(point.score)) for point in results.points]

    def get_chunks(self, tenant_id: str, owner_id: str) -> list[dict]:
        access_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="tenant_id",
                    match=models.MatchValue(value=tenant_id),
                ),
            ],
            should=[
                models.FieldCondition(
                    key="owner_id",
                    match=models.MatchValue(value=owner_id),
                ),
                models.FieldCondition(
                    key="visibility",
                    match=models.MatchValue(value="public"),
                ),
            ],
            min_should=models.MinShould(required=1),
        )

        chunks = []
        offset = None

        while True:
            points, offset = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=access_filter,
                limit=256,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )

            chunks.extend(point.payload for point in points)

            if offset is None:
                break

        return chunks

    def count(self, tenant_id=None, document_id=None):
        conditions = []

        if tenant_id is not None:
            conditions.append(
                models.FieldCondition(
                    key="tenant_id", match=models.MatchValue(value=tenant_id)
                )
            )

        if document_id is not None:
            conditions.append(
                models.FieldCondition(
                    key="document_id", match=models.MatchValue(value=document_id)
                )
            )

        query_filter = models.Filter(must=conditions) if conditions else None

        return self.client.count(
            collection_name=self.collection_name, count_filter=query_filter, exact=True
        ).count
