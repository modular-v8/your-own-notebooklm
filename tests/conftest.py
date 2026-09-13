"""Shared API-test fixtures: an AppState wired entirely from fakes and a
tmp-path store -- no network, no credentials, no on-disk index (AGENTS.md:
the suite must pass with no network access and no API keys)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from raglab.api.app import AppState, build_app
from raglab.api.jobs import JobTable
from raglab.api.store import ConversationStore
from raglab.collections import CollectionRegistry, UserCollectionStore
from raglab.config import RagLabConfig, RetrievalConfig, RoleConfig
from raglab.index.store import ChunkerSettings, NumpyStore, StoredChunk
from raglab.pipelines.agentic import AgenticPipeline
from raglab.pipelines.retrieval import RetrievalPipeline
from raglab.retrieval.retriever import RetrievedChunk
from tests.fakes import FakeProvider


class _FakeEmbedder:
    """No real embedding model in the API test suite -- deterministic and
    offline, same pattern as test_builder.py's."""

    model_id = "fake-embedder"
    dimension = 4

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dimension), dtype=np.float32)
        return np.array([[len(t) % 7 + 1, 0, 0, 0] for t in texts], dtype=np.float32)

DOC_NAME = "doc.md"
DOC_TEXT = "line one\nline two\nthe minimum age is 16\nline four\n"
CHUNK_TEXT = "the minimum age is 16"
CHUNK_START = DOC_TEXT.index(CHUNK_TEXT)
CHUNK_ID = f"{DOC_NAME}:0000"

STORED_CHUNK = StoredChunk(
    chunk_id=CHUNK_ID,
    doc=DOC_NAME,
    ordinal=0,
    char_start=CHUNK_START,
    char_end=CHUNK_START + len(CHUNK_TEXT),
    text=CHUNK_TEXT,
)


class StubRetriever:
    def __init__(self, chunks: list[RetrievedChunk]):
        self.chunks = chunks

    def search(self, query: str, k: int = 5, collection: str | None = None, **kwargs) -> list[RetrievedChunk]:
        return self.chunks[:k]


def default_retriever() -> StubRetriever:
    return StubRetriever(
        [
            RetrievedChunk(
                chunk_id=CHUNK_ID, doc=DOC_NAME, char_start=STORED_CHUNK.char_start,
                char_end=STORED_CHUNK.char_end, text=CHUNK_TEXT, score=0.9,
            )
        ]
    )


DEFAULT_USER_COLLECTION = "docs"


def make_config(reserved_collections: dict[str, list[str]] | None = None) -> RagLabConfig:
    return RagLabConfig(
        answer=RoleConfig(provider="agent_sdk", model="fake"),
        judge=RoleConfig(provider="agent_sdk", model="fake"),
        concurrency=1,
        retrieval=RetrievalConfig(top_k=5, score_threshold=0.35),
        collections=reserved_collections if reserved_collections is not None else {},
    )


def make_state(
    tmp_path: Path,
    *,
    baseline_provider: FakeProvider | None = None,
    agentic_provider: FakeProvider | None = None,
    retriever: StubRetriever | None = None,
    collections: dict[str, list[str]] | None = None,
    user_collections: dict[str, list[str]] | None = None,
) -> AppState:
    """`collections` seeds config.toml's *reserved* set (empty by default --
    most tests don't exercise reserved-name behaviour). `user_collections`
    seeds `collections.json`, the editable set every API route actually
    reads -- defaults to one working collection (`docs`, holding `DOC_NAME`)
    so conversation/chunk tests keep a collection to point at without caring
    about the reserved-name mechanism."""
    baseline_provider = baseline_provider or FakeProvider([])
    retriever = retriever or default_retriever()
    reserved_collections = collections if collections is not None else {}
    editable_collections = user_collections if user_collections is not None else {DEFAULT_USER_COLLECTION: [DOC_NAME]}

    corpus_dir = tmp_path / "corpus"
    uploads_dir = tmp_path / "docs"
    corpus_dir.mkdir(parents=True, exist_ok=True)
    uploads_dir.mkdir(parents=True, exist_ok=True)

    user_store = UserCollectionStore(tmp_path / "collections.json")
    user_store.save(editable_collections)

    return AppState(
        config=make_config(reserved_collections),
        conversation_store=ConversationStore(tmp_path / "conversations"),
        baseline_pipeline=RetrievalPipeline(baseline_provider, retriever, top_k=5, score_threshold=0.35),
        agentic_pipeline=AgenticPipeline(agentic_provider or baseline_provider, retriever, top_k=5, max_calls=5),
        chunks_by_id={CHUNK_ID: STORED_CHUNK},
        doc_texts={DOC_NAME: DOC_TEXT},
        collections=CollectionRegistry(reserved_collections, user_store),
        store=NumpyStore(tmp_path / "index"),
        embedder=_FakeEmbedder(),
        chunking=ChunkerSettings(strategy="fixed", size=900, overlap=150),
        corpus_dir=corpus_dir,
        uploads_dir=uploads_dir,
        index_dir=tmp_path / "index",
        jobs=JobTable(),
    )


def make_app(tmp_path: Path, **kwargs):
    return build_app(make_state(tmp_path, **kwargs))
