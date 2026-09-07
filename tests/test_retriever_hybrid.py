"""Retriever hybrid mode (specs/4-retrieval-optimization T3.3): dense mode
stays byte-identical to today, hybrid mode fuses dense + BM25 via RRF."""

from __future__ import annotations

import numpy as np
import pytest

from raglab.index.store import ChunkerSettings, DocumentManifestEntry, IndexManifest, NumpyStore, StoredChunk
from raglab.retrieval.retriever import Retriever

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
DIMENSION = 2


class _FixedEmbedder:
    """Always embeds to the same vector, regardless of query text -- lets a
    test control the dense ranking independently of BM25's real term match,
    so the two signals can be told apart in the fused result."""

    model_id = EMBEDDING_MODEL
    dimension = DIMENSION

    def __init__(self, vector: list[float]):
        self._vector = np.array(vector, dtype=np.float32)

    def embed_query(self, query: str) -> np.ndarray:
        return self._vector.copy()


def _manifest() -> IndexManifest:
    return IndexManifest(
        embedding_model=EMBEDDING_MODEL,
        dimension=DIMENSION,
        chunker=ChunkerSettings(strategy="fixed", size=900, overlap=150),
        documents={"doc.md": DocumentManifestEntry("sha256:abc", "text/1", 100, 3)},
    )


def _build_store(tmp_path) -> NumpyStore:
    store = NumpyStore(tmp_path / "index")
    chunks = [
        StoredChunk("doc.md:0000", "doc.md", 0, 0, 20, "alpha bravo charlie"),
        StoredChunk("doc.md:0001", "doc.md", 1, 20, 40, "delta echo foxtrot"),
        StoredChunk("doc.md:0002", "doc.md", 2, 40, 60, "golf hotel india"),
    ]
    # Query embedding is fixed at [0, 1] in every test below, so chunk1's
    # vector [0, 1] is always the dense top hit (cosine=1.0), chunk2's
    # [0.7, 0.7] is second (cosine~0.707), chunk0's [1, 0] is last (cosine=0).
    vectors = np.array([[1.0, 0.0], [0.0, 1.0], [0.7, 0.7]], dtype=np.float32)
    store.write(_manifest(), chunks, vectors)
    return store


def test_dense_mode_ignores_lexical_content(tmp_path):
    store = _build_store(tmp_path)
    retriever = Retriever(store, embedder=_FixedEmbedder([0.0, 1.0]))

    # Query text mentions "alpha", a term found only in chunk0 -- pure dense
    # mode must not care, since it never tokenizes the query.
    results = retriever.search("alpha", k=3, mode="dense")

    assert [r.chunk_id for r in results] == ["doc.md:0001", "doc.md:0002", "doc.md:0000"]
    assert results[0].score == pytest.approx(1.0)


def test_hybrid_mode_lets_a_lexical_match_outrank_the_dense_top_hit(tmp_path):
    store = _build_store(tmp_path)
    retriever = Retriever(store, embedder=_FixedEmbedder([0.0, 1.0]))

    # "alpha" only appears in chunk0's text (BM25 rank 1 there, absent from
    # dense's top spot). Dense alone would rank chunk0 last (see test
    # above); fusion should still be able to pull it back to the top.
    results = retriever.search("alpha", k=3, mode="hybrid", candidate_k=3, rrf_k=60)

    assert results[0].chunk_id == "doc.md:0000"


def test_hybrid_mode_k_truncates_fused_results(tmp_path):
    store = _build_store(tmp_path)
    retriever = Retriever(store, embedder=_FixedEmbedder([0.0, 1.0]))

    results = retriever.search("alpha", k=1, mode="hybrid", candidate_k=3)
    assert len(results) == 1


def test_hybrid_mode_respects_collection_filter(tmp_path):
    store = NumpyStore(tmp_path / "index")
    chunks = [
        StoredChunk("doc.md:0000", "doc.md", 0, 0, 20, "alpha bravo charlie", collections=["rules"]),
        StoredChunk("other.md:0000", "other.md", 0, 0, 20, "alpha delta echo", collections=["other"]),
    ]
    vectors = np.array([[0.0, 1.0], [0.0, 1.0]], dtype=np.float32)
    store.write(_manifest(), chunks, vectors)
    retriever = Retriever(store, embedder=_FixedEmbedder([0.0, 1.0]))

    results = retriever.search("alpha", k=5, collection="rules", mode="hybrid", candidate_k=5)

    assert [r.chunk_id for r in results] == ["doc.md:0000"]
