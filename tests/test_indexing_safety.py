"""Index-write safety: a rebuild covers only documents already in the
manifest plus what's explicitly being added or removed -- never a directory
scan -- and every document not touched this call survives byte-for-byte. A
broken invariant restores the prior index rather than leaving a partial
write in place."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from raglab.api.indexing import (
    IndexInvarianceError,
    documents_in_manifest,
    rebuild_index,
    resolve_document,
)
from raglab.corpus import load_document
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
    uploads_dir = tmp_path / "library"
    corpus_dir.mkdir()
    _write(corpus_dir / "eval.md", "Eval corpus content. " * 50)

    store = NumpyStore(tmp_path / "index")
    builder = IndexBuilder(store, _FakeEmbedder())
    return corpus_dir, uploads_dir, store, builder


def test_resolve_document_prefers_uploads_dir(tmp_path):
    corpus_dir, uploads_dir, _, _ = _setup(tmp_path)
    _write(uploads_dir / "uploaded.md", "Uploaded content.")

    from_uploads = resolve_document("uploaded.md", corpus_dir, uploads_dir)
    from_corpus = resolve_document("eval.md", corpus_dir, uploads_dir)

    assert from_uploads.path == uploads_dir / "uploaded.md"
    assert from_corpus.path == corpus_dir / "eval.md"


def test_fresh_install_first_upload_indexes_only_that_document(tmp_path):
    # The fixture sits on disk unindexed -- a build with nothing in the
    # manifest yet and one document being added must not sweep it in
    # (spec: "what gets indexed is defined by the manifest, not disk").
    corpus_dir, uploads_dir, store, builder = _setup(tmp_path)
    _write(uploads_dir / "first.txt", "the first document in a fresh install")
    assert not store.exists()

    results = rebuild_index(
        store, builder, index_dir=store.index_dir, corpus_dir=corpus_dir, uploads_dir=uploads_dir,
        collections={}, adding={"first.txt": load_document(uploads_dir / "first.txt")},
    )

    assert {r.doc for r in results} == {"first.txt"}
    assert set(store.load_manifest().documents) == {"first.txt"}


def test_second_upload_keeps_first_untouched(tmp_path):
    corpus_dir, uploads_dir, store, builder = _setup(tmp_path)
    _write(uploads_dir / "a.txt", "document a, uploaded first")
    rebuild_index(
        store, builder, index_dir=store.index_dir, corpus_dir=corpus_dir, uploads_dir=uploads_dir,
        collections={}, adding={"a.txt": load_document(uploads_dir / "a.txt")},
    )
    before = store.load_manifest().documents["a.txt"]

    _write(uploads_dir / "b.txt", "document b, uploaded second, quite a bit longer")
    rebuild_index(
        store, builder, index_dir=store.index_dir, corpus_dir=corpus_dir, uploads_dir=uploads_dir,
        collections={}, adding={"b.txt": load_document(uploads_dir / "b.txt")},
    )

    after = store.load_manifest()
    assert set(after.documents) == {"a.txt", "b.txt"}
    assert after.documents["a.txt"] == before


def test_removing_drops_a_document_without_touching_the_other(tmp_path):
    corpus_dir, uploads_dir, store, builder = _setup(tmp_path)
    _write(uploads_dir / "a.txt", "document a")
    _write(uploads_dir / "b.txt", "document b, kept")
    rebuild_index(
        store, builder, index_dir=store.index_dir, corpus_dir=corpus_dir, uploads_dir=uploads_dir, collections={},
        adding={
            "a.txt": load_document(uploads_dir / "a.txt"),
            "b.txt": load_document(uploads_dir / "b.txt"),
        },
    )
    before = store.load_manifest().documents["b.txt"]

    rebuild_index(
        store, builder, index_dir=store.index_dir, corpus_dir=corpus_dir, uploads_dir=uploads_dir,
        collections={}, removing=frozenset(["a.txt"]),
    )

    after = store.load_manifest()
    assert set(after.documents) == {"b.txt"}
    assert after.documents["b.txt"] == before


def test_indexing_the_fixture_later_leaves_prior_uploads_untouched(tmp_path):
    # A developer runs `raglab index` (unaffected by this module) after a
    # cloner has already uploaded something -- adding the fixture through
    # this same mechanism must not disturb what's already indexed.
    corpus_dir, uploads_dir, store, builder = _setup(tmp_path)
    _write(uploads_dir / "mine.txt", "a document uploaded before the fixture existed")
    rebuild_index(
        store, builder, index_dir=store.index_dir, corpus_dir=corpus_dir, uploads_dir=uploads_dir,
        collections={}, adding={"mine.txt": load_document(uploads_dir / "mine.txt")},
    )
    before = store.load_manifest().documents["mine.txt"]

    rebuild_index(
        store, builder, index_dir=store.index_dir, corpus_dir=corpus_dir, uploads_dir=uploads_dir,
        collections={}, adding={"eval.md": load_document(corpus_dir / "eval.md")},
    )

    after = store.load_manifest()
    assert set(after.documents) == {"mine.txt", "eval.md"}
    assert after.documents["mine.txt"] == before


def test_broken_invariant_restores_prior_index(tmp_path):
    # Simulates a document that was already indexed being silently modified
    # on disk between two calls, without being named in adding/removing --
    # exactly the identity change the invariant exists to catch.
    corpus_dir, uploads_dir, store, builder = _setup(tmp_path)
    rebuild_index(
        store, builder, index_dir=store.index_dir, corpus_dir=corpus_dir, uploads_dir=uploads_dir,
        collections={}, adding={"eval.md": load_document(corpus_dir / "eval.md")},
    )
    prior_manifest = store.load_manifest()
    prior_chunks = store.load_chunks()

    _write(corpus_dir / "eval.md", "Completely different content that changes the hash and chunk count.")
    _write(uploads_dir / "unrelated.txt", "a document that has nothing to do with eval.md")

    try:
        rebuild_index(
            store, builder, index_dir=store.index_dir, corpus_dir=corpus_dir, uploads_dir=uploads_dir,
            collections={}, adding={"unrelated.txt": load_document(uploads_dir / "unrelated.txt")},
        )
        assert False, "expected IndexInvarianceError"
    except IndexInvarianceError as exc:
        assert exc.doc == "eval.md"

    restored_manifest = store.load_manifest()
    assert restored_manifest.documents == prior_manifest.documents
    assert store.load_chunks() == prior_chunks


def test_documents_in_manifest_empty_when_no_index(tmp_path):
    corpus_dir, uploads_dir, store, _builder = _setup(tmp_path)
    assert not store.exists()

    assert documents_in_manifest(store, corpus_dir, uploads_dir) == {}


def test_documents_in_manifest_resolves_from_either_directory(tmp_path):
    corpus_dir, uploads_dir, store, builder = _setup(tmp_path)
    _write(uploads_dir / "mine.txt", "an uploaded document")
    rebuild_index(
        store, builder, index_dir=store.index_dir, corpus_dir=corpus_dir, uploads_dir=uploads_dir, collections={},
        adding={
            "eval.md": load_document(corpus_dir / "eval.md"),
            "mine.txt": load_document(uploads_dir / "mine.txt"),
        },
    )

    documents = documents_in_manifest(store, corpus_dir, uploads_dir)

    assert set(documents) == {"eval.md", "mine.txt"}
