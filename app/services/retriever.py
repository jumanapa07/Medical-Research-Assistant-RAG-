
import re
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
        rrf_k=60
    ):
        self.store = store
        self.embedding_model = embedding_model

        self.candidate_k = candidate_k
        self.final_k = final_k
        self.rrf_k = rrf_k

        # Load the reranker once, not for every query.
        self.reranker = reranker or CrossEncoder(reranker_model)

  

    def _validate_metadata(self, metadata):

        if not isinstance(metadata, dict):
            raise ValueError("Metadata must be a dictionary")

        missing = [
            field
            for field in REQUIRED_METADATA
            if metadata.get(field) in (None, "")
        ]

        if missing:
            raise ValueError(
                f"Missing required metadata: {missing}"
            )

   

    @staticmethod
    def _tokenize(text):

        return re.findall(
            r"\b\w+\b",
            text.lower()
        )

   
    def _embed_query(self, query):

        embedding = self.embedding_model.encode(
            [query],
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False
        )

        return np.asarray(
            embedding[0],
            dtype=np.float32
        )

    
    def _dense_search(self, query_embedding, metadata):

        return self.store.search(
            query_vec=query_embedding,
            tenant_id=metadata["tenant_id"],
            owner_id=metadata["owner_id"],
            k=self.candidate_k
        )


    def _bm25_search(self, query, metadata):

        chunks = self.store.get_chunks(
            tenant_id=metadata["tenant_id"],owner_id=metadata["owner_id"]
        )

        if not chunks:
            return []

        tokenized_corpus = [
            self._tokenize(chunk.get("text", ""))
            for chunk in chunks
        ]

        bm25 = BM25Okapi(tokenized_corpus)

        query_tokens = self._tokenize(query)

        if not query_tokens:
            return []

        scores = bm25.get_scores(query_tokens)

        ranked_indices = np.argsort(scores)[::-1]

        results = []

        for index in ranked_indices[:self.candidate_k]:

            score = float(scores[index])

            if score <= 0:
                continue

            results.append(
                (chunks[index], score)
            )

        return results


    def _reciprocal_rank_fusion(
        self,
        dense_results,
        bm25_results
    ):

        fused_results = {}

        result_lists = [
            dense_results,
            bm25_results
        ]

        for results in result_lists:

            for rank, (chunk, _) in enumerate(
                results,
                start=1
            ):

                chunk_id = chunk["chunk_id"]

                if chunk_id not in fused_results:

                    fused_results[chunk_id] = {
                        "chunk": chunk,
                        "rrf_score": 0.0
                    }

                fused_results[chunk_id]["rrf_score"] += (
                    1.0 / (self.rrf_k + rank)
                )

        return sorted(
            fused_results.values(),
            key=lambda item: item["rrf_score"],
            reverse=True
        )

    

    def _rerank(self, query, fused_results):

        if not fused_results:
            return []

        chunks = [
            item["chunk"]
            for item in fused_results
        ]

        pairs = [
            (query, chunk.get("text", ""))
            for chunk in chunks
        ]

        scores = self.reranker.predict(
            pairs,
            batch_size=32,
            show_progress_bar=False
        )

        ranked_results = sorted(
            zip(chunks, scores),
            key=lambda item: float(item[1]),
            reverse=True
        )

        return [
            {
                **chunk,
                "rerank_score": float(score)
            }
            for chunk, score in ranked_results[:self.final_k]
        ]

    

    def retrieve(self, query, metadata):

        if not isinstance(query, str) or not query.strip():
            raise ValueError("Query cannot be empty")

        # Validate all six required metadata fields.
        self._validate_metadata(metadata)

        # Generate query embedding.
        query_embedding = self._embed_query(query)

        # Dense retrieval.
        dense_results = self._dense_search(
            query_embedding,
            metadata
        )

        # Keyword retrieval.
        bm25_results = self._bm25_search(
            query,
            metadata
        )

        # Combine both retrieval results.
        fused_results = self._reciprocal_rank_fusion(
            dense_results,
            bm25_results
        )

        # Rerank combined candidates.
        final_results = self._rerank(
            query,
            fused_results
        )

        return final_results
