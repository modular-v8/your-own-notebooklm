"""parse -> chunk -> embed -> write, with per-document incremental rebuild.

A document is re-chunked and re-embedded only when its source hash or
parser identity no longer matches what the index recorded; every other
document's chunks and vectors are carried over untouched.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

import numpy as np

from ..collections import collections_for_doc
from ..corpus import Document
from ..parsers.registry import ParserError, extract_document
from .chunker import CHUNK_OVERLAP, CHUNK_SIZE, chunk_text
from .embedder import Embedder
from .store import (
    ChunkerSettings,
    DocumentManifestEntry,
    IndexManifest,
    StoredChunk,
    VectorStore,
)


@dataclass(frozen=True)
class DocIndexResult:
    doc: str
    chunk_count: int
    error: str | None = None


def _normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


class IndexBuilder:
    def __init__(self, store: VectorStore, embedder: Embedder | None = None):
        self.store = store
        self.embedder = embedder or Embedder()

    def build(
        self, documents: dict[str, Document], collections: dict[str, list[str]] | None = None
    ) -> list[DocIndexResult]:
        collections = collections or {}
        has_existing = self.store.exists()
        existing_manifest = self.store.load_manifest() if has_existing else None
        existing_chunks = self.store.load_chunks() if has_existing else []
        existing_vectors = self.store.load_vectors() if has_existing else np.zeros((0, self.embedder.dimension), dtype=np.float32)

        existing_rows_by_doc: dict[str, list[int]] = {}
        for i, chunk in enumerate(existing_chunks):
            existing_rows_by_doc.setdefault(chunk.doc, []).append(i)

        kept_chunks: list[StoredChunk] = []
        kept_vector_rows: list[np.ndarray] = []
        new_doc_entries: dict[str, DocumentManifestEntry] = {}
        results: list[DocIndexResult] = []

        for name, document in sorted(documents.items()):
            try:
                extracted = extract_document(document)
            except ParserError as exc:
                results.append(DocIndexResult(doc=name, chunk_count=0, error=str(exc)))
                continue

            doc_collections = collections_for_doc(name, collections)

            prior_entry = existing_manifest.documents.get(name) if existing_manifest else None
            unchanged = (
                prior_entry is not None
                and prior_entry.source_sha256 == document.sha256
                and prior_entry.parser == str(extracted.parser)
            )

            if unchanged:
                # Membership-only reindex: a collection reassignment isn't a
                # content change, so refresh `collections` without touching
                # the vector -- no re-embed call, but the field still tracks
                # the current config.toml.
                for row in existing_rows_by_doc.get(name, []):
                    kept_chunks.append(dataclasses.replace(existing_chunks[row], collections=doc_collections))
                    kept_vector_rows.append(existing_vectors[row])
                new_doc_entries[name] = prior_entry
                results.append(DocIndexResult(doc=name, chunk_count=prior_entry.chunk_count))
                continue

            chunks = chunk_text(name, extracted.text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)
            vectors = _normalize(self.embedder.embed([c.text for c in chunks])) if chunks else np.zeros((0, self.embedder.dimension), dtype=np.float32)

            for chunk, vector in zip(chunks, vectors):
                kept_chunks.append(
                    StoredChunk(
                        chunk_id=chunk.chunk_id,
                        doc=chunk.doc,
                        ordinal=chunk.ordinal,
                        char_start=chunk.char_start,
                        char_end=chunk.char_end,
                        text=chunk.text,
                        collections=doc_collections,
                    )
                )
                kept_vector_rows.append(vector)

            new_doc_entries[name] = DocumentManifestEntry(
                source_sha256=document.sha256,
                parser=str(extracted.parser),
                text_chars=len(extracted.text),
                chunk_count=len(chunks),
            )
            results.append(DocIndexResult(doc=name, chunk_count=len(chunks)))

        manifest = IndexManifest(
            embedding_model=self.embedder.model_id,
            dimension=self.embedder.dimension,
            chunker=ChunkerSettings(strategy="fixed", size=CHUNK_SIZE, overlap=CHUNK_OVERLAP),
            documents=new_doc_entries,
        )
        vectors_matrix = (
            np.array(kept_vector_rows, dtype=np.float32)
            if kept_vector_rows
            else np.zeros((0, self.embedder.dimension), dtype=np.float32)
        )
        self.store.write(manifest, kept_chunks, vectors_matrix)
        return results
