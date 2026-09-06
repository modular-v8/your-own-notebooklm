"""Collection-scoped search: out-of-collection chunks never rank into top-k,
even when they'd be the single best global match."""

from __future__ import annotations

import numpy as np

from raglab.index.store import ChunkerSettings, DocumentManifestEntry, IndexManifest, NumpyStore, StoredChunk


def _manifest() -> IndexManifest:
    return IndexManifest(
        embedding_model="BAAI/bge-small-en-v1.5",
        dimension=4,
        chunker=ChunkerSettings(strategy="fixed", size=900, overlap=150),
        documents={
            "rules.pdf": DocumentManifestEntry(source_sha256="sha256:a", parser="pdf/1", text_chars=10, chunk_count=1),
            "trans.md": DocumentManifestEntry(source_sha256="sha256:b", parser="text/1", text_chars=10, chunk_count=1),
        },
    )


def _chunks() -> list[StoredChunk]:
    return [
        StoredChunk(
            chunk_id="rules.pdf:0000",
            doc="rules.pdf",
            ordinal=0,
            char_start=0,
            char_end=10,
            text="rules chunk",
            collections=["rules", "everything"],
        ),
        StoredChunk(
            chunk_id="trans.md:0000",
            doc="trans.md",
            ordinal=0,
            char_start=0,
            char_end=10,
            text="transmissions chunk",
            collections=["transmissions", "everything"],
        ),
    ]


def test_unscoped_search_returns_the_best_global_match(tmp_path):
    store = NumpyStore(tmp_path / "index")
    # trans.md is the best global match (vector [0,1,0,0] vs query [0,1,0,0]).
    vectors = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], dtype=np.float32)
    store.write(_manifest(), _chunks(), vectors)

    query = np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32)
    results = store.search(query, k=2)
    assert results[0][0].chunk_id == "trans.md:0000"


def test_scoped_search_excludes_chunk_outside_collection(tmp_path):
    """The exact failure mode Phase 3 exists to catch: a filter that
    quietly does nothing looks identical to a filter that works, unless
    the excluded chunk would otherwise have ranked first."""
    store = NumpyStore(tmp_path / "index")
    vectors = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], dtype=np.float32)
    store.write(_manifest(), _chunks(), vectors)

    query = np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32)  # best global match is trans.md
    results = store.search(query, k=2, collection="rules")
    assert len(results) == 1
    assert results[0][0].chunk_id == "rules.pdf:0000"


def test_scoped_search_returns_empty_when_collection_has_no_chunks(tmp_path):
    store = NumpyStore(tmp_path / "index")
    vectors = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], dtype=np.float32)
    store.write(_manifest(), _chunks(), vectors)

    query = np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32)
    results = store.search(query, k=5, collection="nonexistent")
    assert results == []
