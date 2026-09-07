"""Rerank stage in Retriever.search (specs/4-retrieval-optimization T4.2)."""

from __future__ import annotations

import numpy as np
import pytest

from raglab.index.store import ChunkerSettings, DocumentManifestEntry, IndexManifest, NumpyStore, StoredChunk
from raglab.retrieval.reranker import RerankedChunk, Reranker
from raglab.retrieval.retriever import Retriever

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
DIMENSION = 2


class _FixedEmbedder:
    model_id = EMBEDDING_MODEL
    dimension = DIMENSION

    def embed_query(self, query: str) -> np.ndarray:
        return np.array([0.0, 1.0], dtype=np.float32)


class _StubReranker:
    """Reverses whatever order it's handed -- deterministic and easy to
    assert on, without touching the real ONNX model."""

    def __init__(self):
        self.calls: list[tuple[str, list[tuple[str, str]]]] = []

    def rerank(self, query: str, candidates: list[tuple[str, str]]) -> list[RerankedChunk]:
        self.calls.append((query, candidates))
        reversed_candidates = list(reversed(candidates))
        n = len(reversed_candidates)
        return [RerankedChunk(chunk_id, float(n - i)) for i, (chunk_id, _) in enumerate(reversed_candidates)]


def _manifest() -> IndexManifest:
    return IndexManifest(
        embedding_model=EMBEDDING_MODEL,
        dimension=DIMENSION,
        chunker=ChunkerSettings(strategy="fixed", size=900, overlap=150),
        documents={"doc.md": DocumentManifestEntry("sha256:abc", "text/1", 100, 4)},
    )


def _build_store(tmp_path) -> NumpyStore:
    store = NumpyStore(tmp_path / "index")
    chunks = [
        StoredChunk("doc.md:0000", "doc.md", 0, 0, 10, "chunk zero"),
        StoredChunk("doc.md:0001", "doc.md", 1, 10, 20, "chunk one"),
        StoredChunk("doc.md:0002", "doc.md", 2, 20, 30, "chunk two"),
        StoredChunk("doc.md:0003", "doc.md", 3, 30, 40, "chunk three"),
    ]
    # Distinct, strictly decreasing dot products against the fixed [0, 1]
    # query vector (1.0/0.9/0.8/0.7) -- deterministic dense order, unlike
    # relying on numpy's unspecified argpartition tie-breaking for equal
    # scores. Dense order is chunk0 > chunk1 > chunk2 > chunk3, so any
    # different order in a test's result came from reranking, not from this.
    vectors = np.array([[0.0, 1.0], [0.0, 0.9], [0.0, 0.8], [0.0, 0.7]], dtype=np.float32)
    store.write(_manifest(), chunks, vectors)
    return store


def test_rerank_stage_fetches_candidate_k_and_truncates_to_k(tmp_path):
    store = _build_store(tmp_path)
    retriever = Retriever(store, embedder=_FixedEmbedder())
    stub = _StubReranker()

    results = retriever.search("q", k=2, mode="dense", candidate_k=4, reranker=stub)

    assert len(results) == 2
    # The stub reverses candidate order; with 4 fetched candidates
    # ["...0000", "...0001", "...0002", "...0003"], the top 2 after
    # reversal are "...0003" then "...0002".
    assert [r.chunk_id for r in results] == ["doc.md:0003", "doc.md:0002"]
    assert stub.calls[0][1] == [
        ("doc.md:0000", "chunk zero"),
        ("doc.md:0001", "chunk one"),
        ("doc.md:0002", "chunk two"),
        ("doc.md:0003", "chunk three"),
    ]


def test_reranking_off_is_a_noop(tmp_path):
    store = _build_store(tmp_path)
    retriever = Retriever(store, embedder=_FixedEmbedder())

    without_reranker = retriever.search("q", k=2, mode="dense")
    with_reranker_none = retriever.search("q", k=2, mode="dense", reranker=None)

    assert without_reranker == with_reranker_none
    assert [r.chunk_id for r in without_reranker] == ["doc.md:0000", "doc.md:0001"]


def test_rejects_candidate_k_less_than_or_equal_to_k(tmp_path):
    store = _build_store(tmp_path)
    retriever = Retriever(store, embedder=_FixedEmbedder())
    stub = _StubReranker()

    with pytest.raises(ValueError, match="candidate_k"):
        retriever.search("q", k=5, mode="dense", candidate_k=5, reranker=stub)


def test_rejects_missing_candidate_k_when_reranking(tmp_path):
    store = _build_store(tmp_path)
    retriever = Retriever(store, embedder=_FixedEmbedder())
    stub = _StubReranker()

    with pytest.raises(ValueError, match="candidate_k"):
        retriever.search("q", k=5, mode="dense", reranker=stub)
