"""Index-write safety net: rebuild the shared index over exactly the
documents already in the manifest plus whatever is explicitly being added
or removed -- never a directory scan -- and verify every document not
being touched keeps its identity, restoring the previous index if it
didn't.

This is the mechanic that makes the eval-corpus fixture optional (spec
amendment, 2026-09-13): "what gets indexed is defined by the manifest, not
by what sits on disk." A fresh clone's empty manifest plus one upload
builds an index of exactly that one document; `evals/corpus/` sits on disk
unindexed until something explicitly adds it (`raglab index`, unchanged).

The invariant generalises the original's eval-corpus-only check ("every
`evals/corpus/` document is unchanged," vacuous when none are indexed) to
"every document not being changed is unchanged" -- correct whether or not
the fixture is part of this call.
"""

from __future__ import annotations

import dataclasses
import shutil
import uuid
from pathlib import Path

from ..collections import collections_for_doc
from ..corpus import Document, load_document
from ..index.builder import DocIndexResult, IndexBuilder
from ..index.store import IndexManifest, VectorStore


class IndexInvarianceError(RuntimeError):
    """Raised when a rebuild would change the identity of a document that
    wasn't part of this call's add/remove request -- the write is rolled
    back rather than left in place (spec: unwanted behavior, "abort rather
    than write")."""

    def __init__(self, doc: str, reason: str):
        self.doc = doc
        self.reason = reason
        super().__init__(f"index rebuild would change untouched document {doc!r}: {reason}")


def resolve_document(name: str, corpus_dir: Path, uploads_dir: Path) -> Document:
    """Load one already-known document by name from whichever directory it
    actually lives in. Upload-time collision checks guarantee a name never
    exists in both, so checking `uploads_dir` first is unambiguous, not a
    priority order."""
    upload_path = uploads_dir / name
    if upload_path.exists():
        return load_document(upload_path)
    return load_document(corpus_dir / name)


def _verify_invariant(protected_names: set[str], before: IndexManifest, after: IndexManifest) -> None:
    for name in protected_names:
        prior = before.documents[name]
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
    adding: dict[str, Document] | None = None,
    removing: frozenset[str] = frozenset(),
) -> list[DocIndexResult]:
    """`collections` should be the *merged* view (`CollectionRegistry.all()`)
    -- this is build-time chunk tagging, not an API-visibility decision, and
    a document already in the manifest may be a reserved-collection member
    whose tagging must stay correct for `raglab eval run`."""
    adding = adding or {}
    had_existing = store.exists()
    before = store.load_manifest() if had_existing else None
    existing_names = set(before.documents) if before is not None else set()

    target_names = (existing_names | set(adding)) - removing
    documents = {
        name: adding[name] if name in adding else resolve_document(name, corpus_dir, uploads_dir)
        for name in target_names
    }
    protected_names = existing_names - removing - set(adding)

    snapshot_dir = _snapshot(index_dir) if had_existing else None
    try:
        results = builder.build(documents, collections)
        if before is not None:
            _verify_invariant(protected_names, before, store.load_manifest())
        return results
    except IndexInvarianceError:
        if snapshot_dir is not None:
            _restore(index_dir, snapshot_dir)
        raise
    finally:
        if snapshot_dir is not None:
            shutil.rmtree(snapshot_dir, ignore_errors=True)


def documents_in_manifest(store: VectorStore, corpus_dir: Path, uploads_dir: Path) -> dict[str, Document]:
    """Every currently-indexed document, resolved back to a `Document` for
    text extraction (citation source panels) -- reads the manifest, never
    the directories, matching `rebuild_index`'s own scoping rule."""
    if not store.exists():
        return {}
    manifest = store.load_manifest()
    return {name: resolve_document(name, corpus_dir, uploads_dir) for name in manifest.documents}


def update_document_collections(store: VectorStore, doc: str, collections: dict[str, list[str]]) -> None:
    """Membership-only rewrite (plan.md): refresh one document's chunks'
    `collections` field without re-embedding. Chunk ids, text, and vectors
    are untouched, so this cannot move any document's identity -- no
    snapshot/verify needed, unlike `rebuild_index`. `collections` should be
    the merged view, same reasoning as `rebuild_index`."""
    manifest = store.load_manifest()
    chunks = store.load_chunks()
    vectors = store.load_vectors()
    doc_collections = collections_for_doc(doc, collections)
    updated = [
        dataclasses.replace(chunk, collections=doc_collections) if chunk.doc == doc else chunk for chunk in chunks
    ]
    store.write(manifest, updated, vectors)
