"""Persistent vector store: manifest.json + chunks.jsonl + vectors.npy.

Brute-force NumPy cosine similarity over a dense float32 matrix. At ~480
chunks today, and well under 50,000 even at Phase 4's largest imaginable
corpus, this is a sub-millisecond operation — an ANN index would add a
dependency and hide the one computation most worth seeing while learning
how retrieval works. `VectorStore` is a Protocol so Phase 4 can replace the
implementation without touching callers.

Row order in `vectors.npy` matches line order in `chunks.jsonl`; vectors are
stored L2-normalized so cosine similarity reduces to a dot product.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol

import numpy as np

MANIFEST_FILENAME = "manifest.json"
CHUNKS_FILENAME = "chunks.jsonl"
VECTORS_FILENAME = "vectors.npy"


@dataclass(frozen=True)
class ChunkerSettings:
    strategy: str
    size: int
    overlap: int


@dataclass(frozen=True)
class DocumentManifestEntry:
    source_sha256: str
    parser: str
    text_chars: int
    chunk_count: int


@dataclass(frozen=True)
class IndexManifest:
    embedding_model: str
    dimension: int
    chunker: ChunkerSettings
    documents: dict[str, DocumentManifestEntry]

    def to_dict(self) -> dict:
        return {
            "embedding_model": self.embedding_model,
            "dimension": self.dimension,
            "chunker": asdict(self.chunker),
            "documents": {name: asdict(entry) for name, entry in self.documents.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> IndexManifest:
        return cls(
            embedding_model=data["embedding_model"],
            dimension=data["dimension"],
            chunker=ChunkerSettings(**data["chunker"]),
            documents={name: DocumentManifestEntry(**entry) for name, entry in data["documents"].items()},
        )


@dataclass(frozen=True)
class StoredChunk:
    chunk_id: str
    doc: str
    ordinal: int
    char_start: int
    char_end: int
    text: str
    # Collections this chunk's document belongs to, per config.toml at
    # index time. Default keeps pre-Phase-3 call sites and fixtures valid.
    collections: list[str] = field(default_factory=list)


class EmbeddingMismatchError(RuntimeError):
    def __init__(self, indexed_model: str, indexed_dim: int, configured_model: str, configured_dim: int):
        self.indexed_model = indexed_model
        self.configured_model = configured_model
        super().__init__(
            f"index was built with {indexed_model} (dim={indexed_dim}); "
            f"configured embedder is {configured_model} (dim={configured_dim})"
        )


class VectorStore(Protocol):
    def exists(self) -> bool: ...
    def load_manifest(self) -> IndexManifest: ...
    def load_chunks(self) -> list[StoredChunk]: ...
    def load_vectors(self) -> np.ndarray: ...
    def write(self, manifest: IndexManifest, chunks: list[StoredChunk], vectors: np.ndarray) -> None: ...
    def search(
        self, query_vector: np.ndarray, k: int, collection: str | None = None
    ) -> list[tuple[StoredChunk, float]]: ...


class NumpyStore:
    def __init__(self, index_dir: Path):
        self.index_dir = index_dir

    def exists(self) -> bool:
        return (self.index_dir / MANIFEST_FILENAME).exists()

    def load_manifest(self) -> IndexManifest:
        raw = json.loads((self.index_dir / MANIFEST_FILENAME).read_text(encoding="utf-8"))
        return IndexManifest.from_dict(raw)

    def load_chunks(self) -> list[StoredChunk]:
        path = self.index_dir / CHUNKS_FILENAME
        if not path.exists():
            return []
        chunks = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            chunks.append(StoredChunk(**row))
        return chunks

    def load_vectors(self) -> np.ndarray:
        path = self.index_dir / VECTORS_FILENAME
        if not path.exists():
            return np.zeros((0, 0), dtype=np.float32)
        return np.load(path)

    def write(self, manifest: IndexManifest, chunks: list[StoredChunk], vectors: np.ndarray) -> None:
        self.index_dir.mkdir(parents=True, exist_ok=True)
        (self.index_dir / MANIFEST_FILENAME).write_text(
            json.dumps(manifest.to_dict(), indent=2), encoding="utf-8"
        )
        with (self.index_dir / CHUNKS_FILENAME).open("w", encoding="utf-8") as f:
            for chunk in chunks:
                f.write(json.dumps(asdict(chunk)) + "\n")
        np.save(self.index_dir / VECTORS_FILENAME, vectors.astype(np.float32))

    def search(
        self, query_vector: np.ndarray, k: int, collection: str | None = None
    ) -> list[tuple[StoredChunk, float]]:
        chunks = self.load_chunks()
        vectors = self.load_vectors()
        if not chunks or vectors.shape[0] == 0:
            return []

        scores = vectors @ query_vector
        if collection is not None:
            # Out-of-collection rows never rank into top-k: masked to -inf
            # rather than filtered out first, so this stays a three-line
            # change against the existing brute-force search.
            mask = np.array([collection in chunk.collections for chunk in chunks])
            scores = np.where(mask, scores, -np.inf)

        top_k = min(k, len(chunks))
        # argpartition is O(n) vs a full O(n log n) sort; fine at this scale either way,
        # but it's the natural way to express "top k" instead of sorting everything.
        top_indices = np.argpartition(-scores, top_k - 1)[:top_k]
        ranked = sorted(top_indices, key=lambda i: -scores[i])
        return [(chunks[i], float(scores[i])) for i in ranked if np.isfinite(scores[i])]
