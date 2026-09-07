"""Corpus-wide top-k retrieval: query embedding -> VectorStore.search().

Hybrid mode fuses this dense search with `BM25Index` via reciprocal rank
fusion (specs/4-retrieval-optimization). The fused score is on RRF's own
scale, not cosine similarity -- callers must not compare it against a
cosine-tuned threshold; see `pipelines/retrieval.py`.

Reranking is a second stage over whichever candidate list dense or hybrid
search produced: fetch `candidate_k`, rerank, truncate to `k`. It composes
with either retrieval mode for free, which is what the eventual "stack the
winners" milestone needs -- `rerank-v1` itself keeps `mode=dense` so the
experiment isolates reranking's own effect.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Literal

import numpy as np

from ..index.embedder import Embedder
from ..index.store import EmbeddingMismatchError, StoredChunk, VectorStore
from .bm25 import BM25Index
from .fusion import DEFAULT_RRF_K, reciprocal_rank_fusion
from .reranker import Reranker

DEFAULT_TOP_K = 5

RetrievalMode = Literal["dense", "hybrid"]


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    doc: str
    char_start: int
    char_end: int
    text: str
    score: float


class Retriever:
    def __init__(self, store: VectorStore, embedder: Embedder | None = None):
        self.store = store
        self.embedder = embedder or Embedder()
        self._bm25_index: BM25Index | None = None

    def _bm25(self) -> BM25Index:
        # Built once, lazily, and only when hybrid mode is actually used --
        # dense-only runs (still the default) pay nothing extra.
        if self._bm25_index is None:
            self._bm25_index = BM25Index(self.store.load_chunks())
        return self._bm25_index

    def _embed_query(self, query: str) -> np.ndarray:
        manifest = self.store.load_manifest()
        if manifest.embedding_model != self.embedder.model_id or manifest.dimension != self.embedder.dimension:
            raise EmbeddingMismatchError(
                manifest.embedding_model, manifest.dimension, self.embedder.model_id, self.embedder.dimension
            )
        query_vector = self.embedder.embed_query(query)
        norm = np.linalg.norm(query_vector)
        return query_vector / norm if norm > 0 else query_vector

    def _to_retrieved(self, chunk: StoredChunk, score: float) -> RetrievedChunk:
        return RetrievedChunk(
            chunk_id=chunk.chunk_id,
            doc=chunk.doc,
            char_start=chunk.char_start,
            char_end=chunk.char_end,
            text=chunk.text,
            score=score,
        )

    def _retrieve_candidates(
        self,
        query: str,
        fetch_k: int,
        collection: str | None,
        mode: RetrievalMode,
        rrf_k: int,
    ) -> list[RetrievedChunk]:
        query_vector = self._embed_query(query)

        if mode == "dense":
            hits = self.store.search(query_vector, fetch_k, collection=collection)
            return [self._to_retrieved(chunk, score) for chunk, score in hits]

        dense_hits = self.store.search(query_vector, fetch_k, collection=collection)
        bm25_hits = self._bm25().search(query, fetch_k, collection=collection)

        dense_ranked_ids = [chunk.chunk_id for chunk, _ in dense_hits]
        bm25_ranked_ids = [hit.chunk_id for hit in bm25_hits]
        fused = reciprocal_rank_fusion([dense_ranked_ids, bm25_ranked_ids], rrf_k=rrf_k)

        # RRF's fused ids can include chunks BM25 surfaced that never made
        # the dense candidate list (or vice versa), so the lookup has to
        # cover every chunk, not just `dense_hits`.
        chunk_by_id = {chunk.chunk_id: chunk for chunk in self._bm25().chunks}
        results = []
        for item in fused[:fetch_k]:
            chunk = chunk_by_id.get(item.chunk_id)
            if chunk is not None:
                results.append(self._to_retrieved(chunk, item.score))
        return results

    def _rerank(self, query: str, candidates: list[RetrievedChunk], reranker: Reranker, k: int) -> list[RetrievedChunk]:
        reranked = reranker.rerank(query, [(c.chunk_id, c.text) for c in candidates])
        candidate_by_id = {c.chunk_id: c for c in candidates}
        return [
            dataclasses.replace(candidate_by_id[r.chunk_id], score=r.score)
            for r in reranked[:k]
            if r.chunk_id in candidate_by_id
        ]

    def search(
        self,
        query: str,
        k: int = DEFAULT_TOP_K,
        collection: str | None = None,
        *,
        mode: RetrievalMode = "dense",
        candidate_k: int | None = None,
        rrf_k: int = DEFAULT_RRF_K,
        reranker: Reranker | None = None,
    ) -> list[RetrievedChunk]:
        if reranker is not None and (candidate_k is None or candidate_k <= k):
            raise ValueError(
                f"reranking needs candidate_k strictly greater than k (got candidate_k={candidate_k}, k={k}) "
                "-- with candidate_k <= k, reranking would only reorder exactly what dense/hybrid already returned"
            )

        fetch_k = candidate_k if reranker is not None else k
        candidates = self._retrieve_candidates(query, fetch_k, collection, mode, rrf_k)

        if reranker is None:
            return candidates[:k]
        return self._rerank(query, candidates, reranker, k)
