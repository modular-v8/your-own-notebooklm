"""parse -> chunk -> embed -> write, with per-document incremental rebuild.

A document is re-chunked and re-embedded only when its source hash or
parser identity no longer matches what the index recorded; every other
document's chunks and vectors are carried over untouched.

Chunking strategy is fixed for the life of an index directory (specs/4-
retrieval-optimization Milestone 6): a `structure` index and a `fixed`
index are different artifacts and must live in different directories
(`experiments.index_subdir_name`) -- `ChunkingMismatchError` refuses to let
one silently overwrite or partially reuse the other's chunks, which the
incremental-rebuild logic above would otherwise do (it only checks a
document's own hash/parser, not whether the index it's writing into was
built with a different chunking config entirely).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

import numpy as np

from ..collections import collections_for_doc
from ..corpus import Document
from ..parsers.registry import ParserError, extract_document
from .chunker import CHUNK_OVERLAP, CHUNK_SIZE, Chunk, chunk_text, chunk_text_structure
from .embedder import Embedder
from .store import (
    ChunkerSettings,
    DocumentManifestEntry,
    IndexManifest,
    StoredChunk,
    VectorStore,
)

DEFAULT_CHUNKING = ChunkerSettings(strategy="fixed", size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)


class ChunkingMismatchError(RuntimeError):
    def __init__(self, index_chunking: ChunkerSettings, requested_chunking: ChunkerSettings):
        self.index_chunking = index_chunking
        self.requested_chunking = requested_chunking
        super().__init__(
            f"index was built with chunking {index_chunking}, but this build requested "
            f"{requested_chunking} -- different chunking strategies need different index "
            "directories, not a shared one"
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


def _chunk(doc_name: str, text: str, chunking: ChunkerSettings) -> list[Chunk]:
    if chunking.strategy == "structure":
        return chunk_text_structure(doc_name, text, max_chars=chunking.size, overlap=chunking.overlap)
    return chunk_text(doc_name, text, size=chunking.size, overlap=chunking.overlap)


class IndexBuilder:
    def __init__(self, store: VectorStore, embedder: Embedder | None = None, *, chunking: ChunkerSettings | None = None):
        self.store = store
        self.embedder = embedder or Embedder()
        self.chunking = chunking or DEFAULT_CHUNKING

    def build(
        self, documents: dict[str, Document], collections: dict[str, list[str]] | None = None
    ) -> list[DocIndexResult]:
        collections = collections or {}
        has_existing = self.store.exists()
        existing_manifest = self.store.load_manifest() if has_existing else None
        if existing_manifest is not None and existing_manifest.chunker != self.chunking:
            raise ChunkingMismatchError(existing_manifest.chunker, self.chunking)
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

            chunks = _chunk(name, extracted.text, self.chunking)
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
            chunker=self.chunking,
            documents=new_doc_entries,
        )
        vectors_matrix = (
            np.array(kept_vector_rows, dtype=np.float32)
            if kept_vector_rows
            else np.zeros((0, self.embedder.dimension), dtype=np.float32)
        )
        self.store.write(manifest, kept_chunks, vectors_matrix)
        return results
