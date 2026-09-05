"""IndexBuilder: incremental rebuild on hash/parser change, parser-failure isolation.

No real embedding model needed -- a small deterministic fake stands in, so
this stays in the offline suite while still exercising the real parser layer
(including a genuine pymupdf failure on a corrupt PDF).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from raglab.corpus import load_document
from raglab.index.builder import IndexBuilder
from raglab.index.store import NumpyStore


class _FakeEmbedder:
    model_id = "fake-embedder"
    dimension = 4

    def __init__(self):
        self.embed_calls: list[list[str]] = []

    def embed(self, texts: list[str]) -> np.ndarray:
        self.embed_calls.append(list(texts))
        if not texts:
            return np.zeros((0, self.dimension), dtype=np.float32)
        # Deterministic, text-dependent so different content -> different vector.
        return np.array([[len(t) % 7 + 1, 0, 0, 0] for t in texts], dtype=np.float32)


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def test_build_indexes_new_documents(tmp_path):
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    _write(corpus_dir / "a.md", "Hello world. " * 100)

    store = NumpyStore(tmp_path / "index")
    embedder = _FakeEmbedder()
    documents = {"a.md": load_document(corpus_dir / "a.md")}

    results = IndexBuilder(store, embedder).build(documents)

    assert results[0].doc == "a.md"
    assert results[0].chunk_count > 0
    assert results[0].error is None

    manifest = store.load_manifest()
    assert "a.md" in manifest.documents
    assert manifest.documents["a.md"].chunk_count == results[0].chunk_count
    assert len(store.load_chunks()) == results[0].chunk_count
    assert store.load_vectors().shape == (results[0].chunk_count, 4)


def test_unchanged_document_is_not_rechunked_or_reembedded(tmp_path):
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    _write(corpus_dir / "a.md", "Some stable content. " * 100)

    store = NumpyStore(tmp_path / "index")
    embedder = _FakeEmbedder()
    documents = {"a.md": load_document(corpus_dir / "a.md")}

    IndexBuilder(store, embedder).build(documents)
    calls_after_first_build = len(embedder.embed_calls)

    chunks_before = store.load_chunks()
    vectors_before = store.load_vectors()

    # Rebuild against the exact same on-disk content.
    documents = {"a.md": load_document(corpus_dir / "a.md")}
    IndexBuilder(store, embedder).build(documents)

    assert len(embedder.embed_calls) == calls_after_first_build  # no new embedding calls
    assert store.load_chunks() == chunks_before
    assert np.array_equal(store.load_vectors(), vectors_before)


def test_changed_document_rebuilds_only_that_document(tmp_path):
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    _write(corpus_dir / "a.md", "Document A original content. " * 50)
    _write(corpus_dir / "b.md", "Document B content, unrelated. " * 50)

    store = NumpyStore(tmp_path / "index")
    embedder = _FakeEmbedder()
    documents = {
        "a.md": load_document(corpus_dir / "a.md"),
        "b.md": load_document(corpus_dir / "b.md"),
    }
    IndexBuilder(store, embedder).build(documents)

    chunks_before = {c.chunk_id: c for c in store.load_chunks()}
    b_chunks_before = [c for c in chunks_before.values() if c.doc == "b.md"]

    # Edit only a.md.
    _write(corpus_dir / "a.md", "Document A has now changed substantially. " * 60)
    documents = {
        "a.md": load_document(corpus_dir / "a.md"),
        "b.md": load_document(corpus_dir / "b.md"),
    }
    embedder.embed_calls.clear()
    IndexBuilder(store, embedder).build(documents)

    chunks_after = {c.chunk_id: c for c in store.load_chunks()}
    b_chunks_after = [c for c in chunks_after.values() if c.doc == "b.md"]

    assert b_chunks_after == b_chunks_before  # untouched
    assert len(embedder.embed_calls) == 1  # only a.md's (changed) chunks were re-embedded
    a_chunks_after = [c for c in chunks_after.values() if c.doc == "a.md"]
    assert a_chunks_after != [c for c in chunks_before.values() if c.doc == "a.md"]


def test_parser_failure_is_recorded_and_other_documents_still_index(tmp_path):
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    _write(corpus_dir / "good.md", "Perfectly fine markdown content. " * 50)
    (corpus_dir / "broken.pdf").write_bytes(b"not a real pdf, just garbage bytes")

    store = NumpyStore(tmp_path / "index")
    embedder = _FakeEmbedder()
    documents = {
        "good.md": load_document(corpus_dir / "good.md"),
        "broken.pdf": load_document(corpus_dir / "broken.pdf"),
    }

    results = IndexBuilder(store, embedder).build(documents)
    by_doc = {r.doc: r for r in results}

    assert by_doc["broken.pdf"].error is not None
    assert by_doc["good.md"].error is None
    assert by_doc["good.md"].chunk_count > 0

    manifest = store.load_manifest()
    assert "good.md" in manifest.documents
    assert "broken.pdf" not in manifest.documents
