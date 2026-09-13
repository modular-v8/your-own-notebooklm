"""Index-write safety net (plan.md): rebuild the shared index over every
eval-corpus and uploaded document, verify no `evals/corpus/` document's
identity moved, and restore the previous index if it did.

The spec's central guarantee -- `evals/corpus/` must stay byte-for-byte
reproducible -- made mechanical on every write this module performs, not
just checked in a test. `IndexBuilder`'s own incremental rebuild already
means an unchanged document's chunk ids and hash cannot move on their own;
this exists to catch an orchestration bug here (e.g. an eval document
dropped from the `documents` dict by mistake) before it reaches disk.
"""

from __future__ import annotations

import dataclasses
import shutil
import uuid
from pathlib import Path

from ..collections import collections_for_doc
from ..corpus import Document, load_corpus
from ..index.builder import DocIndexResult, IndexBuilder
from ..index.store import IndexManifest, VectorStore


class IndexInvarianceError(RuntimeError):
    """Raised when a rebuild would change an eval-corpus document's
    identity -- the write is rolled back rather than left in place
    (spec: unwanted behavior, "abort rather than write")."""

    def __init__(self, doc: str, reason: str):
        self.doc = doc
        self.reason = reason
        super().__init__(f"index rebuild would change eval corpus document {doc!r}: {reason}")


def load_all_documents(corpus_dir: Path, uploads_dir: Path) -> dict[str, Document]:
    """The eval corpus and uploaded documents as one combined set -- "one
    index, shared" (spec: data & integrations). Upload-time name-collision
    checks already guarantee the two never name the same document."""
    documents = load_corpus(corpus_dir)
    if uploads_dir.exists():
        documents.update(load_corpus(uploads_dir))
    return documents


def _verify_invariant(eval_doc_names: set[str], before: IndexManifest, after: IndexManifest) -> None:
    for name in eval_doc_names:
        prior = before.documents.get(name)
        if prior is None:
            continue  # wasn't indexed before this write either -- nothing to protect
        current = after.documents.get(name)
        if current is None:
            raise IndexInvarianceError(name, "dropped from the index")
        if current.source_sha256 != prior.source_sha256:
            raise IndexInvarianceError(name, "content hash changed")
        if current.chunk_count != prior.chunk_count:
            raise IndexInvarianceError(name, f"chunk count changed ({prior.chunk_count} -> {current.chunk_count})")


def _snapshot(index_dir: Path) -> Path:
    snapshot_dir = index_dir.parent / f".{index_dir.name}.snapshot-{uuid.uuid4().hex}"
    shutil.copytree(index_dir, snapshot_dir)
    return snapshot_dir


def _restore(index_dir: Path, snapshot_dir: Path) -> None:
    shutil.rmtree(index_dir)
    shutil.copytree(snapshot_dir, index_dir)


def rebuild_index(
    store: VectorStore,
    builder: IndexBuilder,
    *,
    index_dir: Path,
    corpus_dir: Path,
    uploads_dir: Path,
    collections: dict[str, list[str]],
    eval_doc_names: frozenset[str],
) -> list[DocIndexResult]:
    """`eval_doc_names` is the eval corpus's file list as captured once at
    server startup (`AppState.eval_doc_names`), not re-scanned from
    `corpus_dir` here -- the exact failure mode this guards against (an eval
    document going missing from disk between requests) would otherwise
    silently shrink the set it's being checked against, defeating the check."""
    documents = load_all_documents(corpus_dir, uploads_dir)

    had_existing = store.exists()
    before = store.load_manifest() if had_existing else None
    snapshot_dir = _snapshot(index_dir) if had_existing else None

    try:
        results = builder.build(documents, collections)
        if before is not None:
            _verify_invariant(eval_doc_names, before, store.load_manifest())
        return results
    except IndexInvarianceError:
        if snapshot_dir is not None:
            _restore(index_dir, snapshot_dir)
        raise
    finally:
        if snapshot_dir is not None:
            shutil.rmtree(snapshot_dir, ignore_errors=True)


def update_document_collections(store: VectorStore, doc: str, collections: dict[str, list[str]]) -> None:
    """Membership-only rewrite (plan.md): refresh one document's chunks'
    `collections` field without re-embedding. Chunk ids, text, and vectors
    are untouched, so this cannot move any document's identity -- no
    snapshot/verify needed, unlike `rebuild_index`."""
    manifest = store.load_manifest()
    chunks = store.load_chunks()
    vectors = store.load_vectors()
    doc_collections = collections_for_doc(doc, collections)
    updated = [
        dataclasses.replace(chunk, collections=doc_collections) if chunk.doc == doc else chunk for chunk in chunks
    ]
    store.write(manifest, updated, vectors)
