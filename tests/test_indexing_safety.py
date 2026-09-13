"""Index-write safety: eval-corpus documents survive an upload rebuild
byte-for-byte, and a broken invariant restores the prior index rather than
leaving a partial write in place."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from raglab.api.indexing import IndexInvarianceError, load_all_documents, rebuild_index
from raglab.index.builder import IndexBuilder
from raglab.index.store import NumpyStore


class _FakeEmbedder:
    model_id = "fake-embedder"
    dimension = 4

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dimension), dtype=np.float32)
        return np.array([[len(t) % 7 + 1, 0, 0, 0] for t in texts], dtype=np.float32)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _setup(tmp_path: Path) -> tuple[Path, Path, NumpyStore, IndexBuilder]:
    corpus_dir = tmp_path / "corpus"
    uploads_dir = tmp_path / "docs"
    corpus_dir.mkdir()
    _write(corpus_dir / "eval.md", "Eval corpus content. " * 50)

    store = NumpyStore(tmp_path / "index")
    builder = IndexBuilder(store, _FakeEmbedder())
    return corpus_dir, uploads_dir, store, builder


def test_load_all_documents_merges_corpus_and_uploads(tmp_path):
    corpus_dir, uploads_dir, _, _ = _setup(tmp_path)
    _write(uploads_dir / "uploaded.md", "Uploaded content.")

    documents = load_all_documents(corpus_dir, uploads_dir)

    assert set(documents) == {"eval.md", "uploaded.md"}


def test_rebuild_indexes_uploaded_doc_without_touching_eval_doc(tmp_path):
    corpus_dir, uploads_dir, store, builder = _setup(tmp_path)
    eval_names = frozenset(["eval.md"])
    rebuild_index(store, builder, index_dir=store.index_dir, corpus_dir=corpus_dir, uploads_dir=uploads_dir, collections={}, eval_doc_names=eval_names)
    before = store.load_manifest().documents["eval.md"]

    _write(uploads_dir / "uploaded.md", "Freshly uploaded content, quite a bit longer than before.")
    rebuild_index(store, builder, index_dir=store.index_dir, corpus_dir=corpus_dir, uploads_dir=uploads_dir, collections={}, eval_doc_names=eval_names)

    after = store.load_manifest()
    assert "uploaded.md" in after.documents
    assert after.documents["eval.md"] == before


def test_broken_invariant_restores_prior_index(tmp_path):
    corpus_dir, uploads_dir, store, builder = _setup(tmp_path)
    eval_names = frozenset(["eval.md"])
    rebuild_index(store, builder, index_dir=store.index_dir, corpus_dir=corpus_dir, uploads_dir=uploads_dir, collections={}, eval_doc_names=eval_names)
    prior_manifest = store.load_manifest()
    prior_chunks = store.load_chunks()

    # Simulate an orchestration bug: the eval doc vanishes from corpus_dir
    # between builds, so the rebuild would silently drop it from the index.
    # eval_names is captured once at startup (like AppState.eval_doc_names),
    # so it still names "eval.md" even though corpus_dir no longer does --
    # that's exactly what makes the check able to catch this.
    (corpus_dir / "eval.md").unlink()

    try:
        rebuild_index(store, builder, index_dir=store.index_dir, corpus_dir=corpus_dir, uploads_dir=uploads_dir, collections={}, eval_doc_names=eval_names)
        assert False, "expected IndexInvarianceError"
    except IndexInvarianceError as exc:
        assert exc.doc == "eval.md"

    restored_manifest = store.load_manifest()
    assert restored_manifest.documents == prior_manifest.documents
    assert store.load_chunks() == prior_chunks


def test_first_build_has_nothing_to_verify_against(tmp_path):
    corpus_dir, uploads_dir, store, builder = _setup(tmp_path)
    assert not store.exists()

    results = rebuild_index(
        store, builder, index_dir=store.index_dir, corpus_dir=corpus_dir, uploads_dir=uploads_dir, collections={},
        eval_doc_names=frozenset(["eval.md"]),
    )

    assert {r.doc for r in results} == {"eval.md"}
