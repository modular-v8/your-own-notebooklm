"""NumpyStore round-trip and the embedding-model/dimension mismatch refusal.

No real embeddings needed here -- vectors are synthetic and the mismatch
check happens before any embedding call, so a stub embedder (just
`model_id`/`dimension`) is enough.
"""

from __future__ import annotations

import numpy as np
import pytest

from raglab.index.store import (
    ChunkerSettings,
    DocumentManifestEntry,
    EmbeddingMismatchError,
    IndexManifest,
    NumpyStore,
    StoredChunk,
)
from raglab.retrieval.retriever import Retriever


class _StubEmbedder:
    def __init__(self, model_id: str, dimension: int):
        self.model_id = model_id
        self.dimension = dimension


def _sample_manifest(model="BAAI/bge-small-en-v1.5", dim=4) -> IndexManifest:
    return IndexManifest(
        embedding_model=model,
        dimension=dim,
        chunker=ChunkerSettings(strategy="fixed", size=900, overlap=150),
        documents={
            "doc.md": DocumentManifestEntry(
                source_sha256="sha256:abc", parser="text/1", text_chars=100, chunk_count=2
            )
        },
    )


def _sample_chunks() -> list[StoredChunk]:
    return [
        StoredChunk(chunk_id="doc.md:0000", doc="doc.md", ordinal=0, char_start=0, char_end=50, text="first chunk"),
        StoredChunk(chunk_id="doc.md:0001", doc="doc.md", ordinal=1, char_start=50, char_end=100, text="second chunk"),
    ]


def test_write_and_load_round_trips(tmp_path):
    store = NumpyStore(tmp_path / "index")
    manifest = _sample_manifest()
    chunks = _sample_chunks()
    vectors = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], dtype=np.float32)

    assert not store.exists()
    store.write(manifest, chunks, vectors)
    assert store.exists()

    loaded_manifest = store.load_manifest()
    assert loaded_manifest == manifest

    loaded_chunks = store.load_chunks()
    assert loaded_chunks == chunks

    loaded_vectors = store.load_vectors()
    assert np.array_equal(loaded_vectors, vectors)


def test_search_returns_closest_vector_first(tmp_path):
    store = NumpyStore(tmp_path / "index")
    manifest = _sample_manifest()
    chunks = _sample_chunks()
    vectors = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], dtype=np.float32)
    store.write(manifest, chunks, vectors)

    query = np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32)
    results = store.search(query, k=2)
    assert results[0][0].chunk_id == "doc.md:0001"
    assert results[0][1] == pytest.approx(1.0)


def test_retriever_refuses_mismatched_embedding_model(tmp_path):
    store = NumpyStore(tmp_path / "index")
    store.write(_sample_manifest(model="BAAI/bge-small-en-v1.5", dim=4), _sample_chunks(), np.zeros((2, 4), dtype=np.float32))

    retriever = Retriever(store, embedder=_StubEmbedder(model_id="some-other-model", dimension=4))
    with pytest.raises(EmbeddingMismatchError) as exc_info:
        retriever.search("query")
    assert "bge-small-en-v1.5" in str(exc_info.value)
    assert "some-other-model" in str(exc_info.value)


def test_retriever_refuses_mismatched_dimension(tmp_path):
    store = NumpyStore(tmp_path / "index")
    store.write(_sample_manifest(model="BAAI/bge-small-en-v1.5", dim=4), _sample_chunks(), np.zeros((2, 4), dtype=np.float32))

    retriever = Retriever(store, embedder=_StubEmbedder(model_id="BAAI/bge-small-en-v1.5", dimension=8))
    with pytest.raises(EmbeddingMismatchError):
        retriever.search("query")
