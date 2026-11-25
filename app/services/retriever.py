import re
import threading
import time

import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder

from app.services.ingestion import REQUIRED_METADATA


class Retriever:

    def __init__(
        self,
        store,
        embedding_model,
        reranker=None,
        reranker_model="cross-encoder/ms-marco-MiniLM-L-6-v2",
        candidate_k=20,
        final_k=5,
        rrf_k=60,
        rerank_top_n=None,        # how many fused candidates go to the cross-encoder
        bm25_ttl_seconds=600,     # safety net; writes also invalidate explicitly
    ):
        self.store = store
        self.embedding_model = embedding_model

        self.candidate_k = candidate_k
        self.final_k = final_k
        self.rrf_k = rrf_k
        # Fusing two lists of 20 yields up to 40 chunks; reranking only the best
        # `candidate_k` of them roughly halves the most expensive step.
        self.rerank_top_n = rerank_top_n or candidate_k

        # Load the reranker once, not for every query.
        self.reranker = reranker or CrossEncoder(reranker_model)

        # BM25 index per (tenant_id, owner_id), built once and reused.
        self._bm25_ttl = bm25_ttl_seconds
        self._bm25_cache = {}
        self._cache_lock = threading.Lock()

    def invalidate(self, tenant_id=None, owner_id=None):
        """Drop cached keyword indexes (all, one tenant, or one tenant/owner)."""
        with self._cache_lock:
            if tenant_id is None:
                self._bm25_cache.clear()
                return
            for key in list(self._bm25_cache):
                if key[0] == tenant_id and (owner_id is None or key[1] == owner_id):
                    del self._bm25_cache[key]

    def _get_bm25_index(self, metadata):
        key = (metadata["tenant_id"], metadata["owner_id"])
        now = time.monotonic()

        with self._cache_lock:
            entry = self._bm25_cache.get(key)
            if entry and now - entry["built_at"] < self._bm25_ttl:
                return entry

        # Build outside the lock so other tenants are not blocked.
        chunks = self.store.get_chunks(
            tenant_id=metadata["tenant_id"],
            owner_id=metadata["owner_id"],
        )

        entry = {
            "chunks": chunks,
            "bm25": (
                BM25Okapi([self._tokenize(c.get("text", "")) for c in chunks])
                if chunks
                else None
            ),
            "built_at": now,
        }

        with self._cache_lock:
            self._bm25_cache[key] = entry

        return entry

    def _validate_metadata(self, metadata):

        if not isinstance(metadata, dict):
            raise ValueError("Metadata must be a dictionary")

        missing = [
            field
            for field in REQUIRED_METADATA
            if metadata.get(field) in (None, "")
        ]

        if missing:
            raise ValueError(f"Missing required metadata: {missing}")

    @staticmethod
    def _tokenize(text):
        return re.findall(r"\b\w+\b", text.lower())

    def _embed_query(self, query):

        embedding = self.embedding_model.encode(
            [query],
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )

        return np.asarray(embedding[0], dtype=np.float32)

    def _dense_search(self, query_embedding, metadata):

        return self.store.search(
            query_vec=query_embedding,
            tenant_id=metadata["tenant_id"],
            owner_id=metadata["owner_id"],
            k=self.candidate_k,
        )

    def _bm25_search(self, query, metadata):

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        entry = self._get_bm25_index(metadata)
        if entry["bm25"] is None:
            return []

        chunks = entry["chunks"]
        scores = entry["bm25"].get_scores(query_tokens)

        k = min(self.candidate_k, len(scores))
        top = np.argpartition(scores, -k)[-k:]
        top = top[np.argsort(scores[top])[::-1]]

        return [
            (chunks[i], float(scores[i]))
            for i in top
            if scores[i] > 0
        ]

    def _reciprocal_rank_fusion(self, dense_results, bm25_results):

        fused_results = {}

        for results in (dense_results, bm25_results):
            for rank, (chunk, _) in enumerate(results, start=1):

                chunk_id = chunk["chunk_id"]

                if chunk_id not in fused_results:
                    fused_results[chunk_id] = {"chunk": chunk, "rrf_score": 0.0}

                fused_results[chunk_id]["rrf_score"] += 1.0 / (self.rrf_k + rank)

        return sorted(
            fused_results.values(),
            key=lambda item: item["rrf_score"],
            reverse=True,
        )

    def _rerank(self, query, fused_results):

        if not fused_results:
            return []

        chunks = [item["chunk"] for item in fused_results[: self.rerank_top_n]]

        scores = self.reranker.predict(
            [(query, chunk.get("text", "")) for chunk in chunks],
            batch_size=32,
            show_progress_bar=False,
        )

        ranked_results = sorted(
            zip(chunks, scores),
            key=lambda item: float(item[1]),
            reverse=True,
        )

        return [
            {**chunk, "rerank_score": float(score)}
            for chunk, score in ranked_results[: self.final_k]
        ]

    def retrieve(self, query, metadata):

        if not isinstance(query, str) or not query.strip():
            raise ValueError("Query cannot be empty")

        self._validate_metadata(metadata)

        query_embedding = self._embed_query(query)

        dense_results = self._dense_search(query_embedding, metadata)
        bm25_results = self._bm25_search(query, metadata)

        fused_results = self._reciprocal_rank_fusion(dense_results, bm25_results)

        return self._rerank(query, fused_results)
