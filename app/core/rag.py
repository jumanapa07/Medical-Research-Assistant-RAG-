"""
Single source of truth for the RAG stack.

Everything that must stay identical between ingestion and retrieval
(embedding model, collection, vector store) is created ONCE here and shared:

    * one SentenceTransformer instance, used by the pipeline AND the retriever
    * one vector store, used by ingestion AND retrieval
    * one reranker, loaded once

Services are built lazily on first use, so importing this module is cheap.
Existing imports keep working:  from app.services.rag import retriever
"""

import os
import threading
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv
from sentence_transformers import CrossEncoder, SentenceTransformer

from app.services.generation import GenerationService
from app.services.ingestion import IngestionPipeline
from app.services.ingestion_service import DocumentIngestionService
from app.services.retriever import Retriever
from app.services.vector_store import QdrantVectorStore

load_dotenv()


@dataclass(frozen=True)
class RAGSettings:
    collection_name: str = "medical_research"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    qdrant_url: str = "http://localhost:6333"
    chunk_size: int = 400  # tokens
    chunk_overlap: int = 60  # tokens
    candidate_k: int = 20
    final_k: int = 5
    device: str | None = None  # None = auto (cuda / mps / cpu)

    @classmethod
    def from_env(cls) -> "RAGSettings":
        d = cls()
        return cls(
            collection_name=os.getenv("RAG_COLLECTION", d.collection_name),
            embedding_model=os.getenv("RAG_EMBEDDING_MODEL", d.embedding_model),
            reranker_model=os.getenv("RAG_RERANKER_MODEL", d.reranker_model),
            qdrant_url=os.getenv("QDRANT_URL", d.qdrant_url),
            chunk_size=int(os.getenv("RAG_CHUNK_SIZE", d.chunk_size)),
            chunk_overlap=int(os.getenv("RAG_CHUNK_OVERLAP", d.chunk_overlap)),
            candidate_k=int(os.getenv("RAG_CANDIDATE_K", d.candidate_k)),
            final_k=int(os.getenv("RAG_FINAL_K", d.final_k)),
            device=os.getenv("RAG_DEVICE") or None,
        )


class _InvalidatingStore:
    """Wraps the vector store; any write invalidates the retriever's keyword index."""

    def __init__(self, store: Any, on_change):
        self._store = store
        self._on_change = on_change

    def __getattr__(self, name: str):  # search, get_chunks, ... pass straight through
        return getattr(self._store, name)

    def upsert(self, chunks, embeddings, *args, **kwargs):
        result = self._store.upsert(chunks, embeddings, *args, **kwargs)
        for tenant_id in {c.get("tenant_id") for c in chunks}:
            self._on_change(tenant_id)
        return result

    def delete_document(self, tenant_id, *args, **kwargs):
        result = self._store.delete_document(tenant_id, *args, **kwargs)
        self._on_change(tenant_id)
        return result


@dataclass(frozen=True)
class RAGServices:
    settings: RAGSettings
    embedding_model: SentenceTransformer
    reranker: CrossEncoder
    pipeline: IngestionPipeline
    vector_store: Any
    ingestion_service: DocumentIngestionService
    retriever: Retriever
    generation_service: GenerationService

    def warmup(self) -> None:
        """Run one dummy embedding + rerank so the first user request isn't slow."""
        self.embedding_model.encode(["warmup"], normalize_embeddings=True)
        self.reranker.predict([("warmup", "warmup")])


_lock = threading.Lock()
_services: RAGServices | None = None


def _build() -> RAGServices:
    s = RAGSettings.from_env()

    # ONE embedding model object, shared by ingestion and retrieval.
    embedding_model = SentenceTransformer(s.embedding_model, device=s.device)
    reranker = CrossEncoder(s.reranker_model, device=s.device)

    pipeline = IngestionPipeline(
        collection_name=s.collection_name,
        embedding_model=s.embedding_model,
        chunk_size=s.chunk_size,
        chunk_overlap=s.chunk_overlap,
        model=embedding_model,  # reuse, do not load a second copy
    )

    qdrant = QdrantVectorStore(
        collection_name=s.collection_name,
        vector_size=pipeline.embedding_dimension,
        url=s.qdrant_url,
    )

    retriever = Retriever(
        store=None,  # set below once the invalidating wrapper exists
        embedding_model=embedding_model,
        reranker=reranker,
        candidate_k=s.candidate_k,
        final_k=s.final_k,
    )

    vector_store = _InvalidatingStore(qdrant, on_change=retriever.invalidate)
    retriever.store = vector_store

    ingestion_service = DocumentIngestionService(
        pipeline=pipeline,
        vector_store=vector_store,
    )

    # Guard against drift between ingestion and retrieval.
    assert retriever.embedding_model is pipeline.model, "embedding models diverged"

    return RAGServices(
        settings=s,
        embedding_model=embedding_model,
        reranker=reranker,
        pipeline=pipeline,
        vector_store=vector_store,
        ingestion_service=ingestion_service,
        retriever=retriever,
        generation_service=GenerationService(),
    )


def get_rag() -> RAGServices:
    """Return the shared RAG services, building them on first call (thread-safe)."""
    global _services
    if _services is None:
        with _lock:
            if _services is None:
                _services = _build()
    return _services


# Backward compatibility: `from app.core.rag import retriever` etc. still works,
# but nothing heavy is loaded until one of these names is actually accessed.
_EXPORTS = {
    "pipeline",
    "embedding_model",
    "vector_store",
    "ingestion_service",
    "retriever",
    "generation_service",
}


def __getattr__(name: str):
    if name in _EXPORTS:
        return getattr(get_rag(), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")