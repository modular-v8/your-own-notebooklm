"""Corpus-wide top-k retrieval: query embedding -> VectorStore.search()."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..index.embedder import Embedder
from ..index.store import EmbeddingMismatchError, VectorStore

DEFAULT_TOP_K = 5


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

    def search(
        self, query: str, k: int = DEFAULT_TOP_K, collection: str | None = None
    ) -> list[RetrievedChunk]:
        manifest = self.store.load_manifest()
        if manifest.embedding_model != self.embedder.model_id or manifest.dimension != self.embedder.dimension:
            raise EmbeddingMismatchError(
                manifest.embedding_model, manifest.dimension, self.embedder.model_id, self.embedder.dimension
            )

        query_vector = self.embedder.embed_query(query)
        norm = np.linalg.norm(query_vector)
        if norm > 0:
            query_vector = query_vector / norm

        hits = self.store.search(query_vector, k, collection=collection)
        return [
            RetrievedChunk(
                chunk_id=chunk.chunk_id,
                doc=chunk.doc,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
                text=chunk.text,
                score=score,
            )
            for chunk, score in hits
        ]
