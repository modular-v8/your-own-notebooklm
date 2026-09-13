"""FastAPI app: transport only, no answering logic. Wires the existing
`raglab` modules (config, retriever, pipelines) into HTTP routes and,
optionally, mounts the built frontend as static files.

`build_app(state)` takes already-constructed dependencies so tests can
inject fakes without a real provider, credential, or index (AGENTS.md: the
suite must pass with no network access and no API keys). `create_app(...)`
is the real wiring `raglab serve` uses.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from ..collections import CollectionRegistry, UserCollectionStore
from ..config import DEFAULT_CONFIG_PATH, RagLabConfig
from ..corpus import load_corpus
from ..experiments import DEFAULT_EXPERIMENTS_PATH, load_experiments
from ..index.embedder import Embedder
from ..index.store import ChunkerSettings, NumpyStore, StoredChunk, VectorStore
from ..parsers.registry import extract_document
from ..pipelines.agentic import AgenticPipeline
from ..pipelines.retrieval import RetrievalPipeline
from ..providers.base import LLMProvider
from ..providers.registry import build_provider
from ..retrieval.retriever import Retriever
from .indexing import load_all_documents
from .jobs import JobTable
from . import routes_chunks, routes_collections, routes_conversations, routes_documents
from .store import DEFAULT_CONVERSATIONS_DIR, ConversationStore

DEFAULT_CORPUS_DIR = Path("evals/corpus")
DEFAULT_INDEX_DIR = Path("evals/index/fixed-900-150")
DEFAULT_UPLOADS_DIR = Path("docs")
DEFAULT_COLLECTIONS_PATH = Path("collections.json")
DEFAULT_STATIC_DIR = Path("web/dist")
AGENTIC_EXPERIMENT_NAME = "agentic-v1"


@dataclass
class AppState:
    config: RagLabConfig
    conversation_store: ConversationStore
    baseline_pipeline: RetrievalPipeline
    agentic_pipeline: AgenticPipeline
    chunks_by_id: dict[str, StoredChunk]
    doc_texts: dict[str, str]
    collections: CollectionRegistry
    store: VectorStore
    embedder: Embedder
    chunking: ChunkerSettings
    corpus_dir: Path
    uploads_dir: Path
    index_dir: Path
    # Snapshotted once at startup -- never re-derived from corpus_dir at
    # request time, so a document accidentally missing from disk can't
    # shrink the set an index rebuild protects (see api/indexing.py).
    eval_doc_names: frozenset[str]
    jobs: JobTable = field(default_factory=JobTable)
    index_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def refresh_chunk_cache(self) -> None:
        """Re-reads the index and every known document's text after a
        rebuild. Mutates the existing dicts in place rather than replacing
        them, since route handlers hold a reference to `state`, not a copy."""
        chunks = self.store.load_chunks()
        documents = load_all_documents(self.corpus_dir, self.uploads_dir)
        doc_texts = {name: extract_document(doc).text for name, doc in documents.items()}

        self.chunks_by_id.clear()
        self.chunks_by_id.update({c.chunk_id: c for c in chunks})
        self.doc_texts.clear()
        self.doc_texts.update(doc_texts)


def build_app(state: AppState, *, static_dir: Path | None = None) -> FastAPI:
    app = FastAPI(title="raglab")
    app.state.raglab = state

    app.include_router(routes_collections.router)
    app.include_router(routes_documents.router)
    app.include_router(routes_conversations.router)
    app.include_router(routes_chunks.router)

    if static_dir is not None and static_dir.exists():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")

    return app


def _build_pipelines(provider: LLMProvider, retriever: Retriever, config: RagLabConfig, experiments_path: Path):
    baseline = RetrievalPipeline(
        provider, retriever, top_k=config.retrieval.top_k, score_threshold=config.retrieval.score_threshold
    )

    experiments = load_experiments(experiments_path)
    if AGENTIC_EXPERIMENT_NAME not in experiments:
        raise RuntimeError(f"{experiments_path}: missing required {AGENTIC_EXPERIMENT_NAME!r} entry (escalation target)")
    experiment = experiments[AGENTIC_EXPERIMENT_NAME]
    if experiment.agentic is None:
        raise RuntimeError(f"{experiments_path}: {AGENTIC_EXPERIMENT_NAME!r} has no [agentic] section")

    agentic = AgenticPipeline(
        provider,
        retriever,
        top_k=experiment.retrieval.k,
        max_calls=experiment.agentic.max_calls,
        prune_top_n=experiment.agentic.prune_top_n,
        tight_citations=experiment.agentic.tight_citations,
    )
    return baseline, agentic


def create_app(
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    corpus_dir: Path = DEFAULT_CORPUS_DIR,
    index_dir: Path = DEFAULT_INDEX_DIR,
    uploads_dir: Path = DEFAULT_UPLOADS_DIR,
    collections_path: Path = DEFAULT_COLLECTIONS_PATH,
    conversations_dir: Path = DEFAULT_CONVERSATIONS_DIR,
    experiments_path: Path = DEFAULT_EXPERIMENTS_PATH,
    static_dir: Path | None = DEFAULT_STATIC_DIR,
) -> FastAPI:
    config = RagLabConfig.load(config_path)

    store = NumpyStore(index_dir)
    if not store.exists():
        raise RuntimeError(f"No index at {index_dir}. Run `raglab index` first.")
    manifest = store.load_manifest()
    retriever = Retriever(store)

    uploads_dir.mkdir(parents=True, exist_ok=True)
    documents = load_all_documents(corpus_dir, uploads_dir)
    doc_texts = {name: extract_document(doc).text for name, doc in documents.items()}

    registry = CollectionRegistry(config.collections, UserCollectionStore(collections_path))

    provider = build_provider(config.answer.provider, config.answer.model)
    baseline_pipeline, agentic_pipeline = _build_pipelines(provider, retriever, config, experiments_path)

    state = AppState(
        config=config,
        conversation_store=ConversationStore(conversations_dir),
        baseline_pipeline=baseline_pipeline,
        agentic_pipeline=agentic_pipeline,
        chunks_by_id={chunk.chunk_id: chunk for chunk in store.load_chunks()},
        doc_texts=doc_texts,
        collections=registry,
        store=store,
        embedder=Embedder(),
        chunking=manifest.chunker,
        corpus_dir=corpus_dir,
        uploads_dir=uploads_dir,
        index_dir=index_dir,
        eval_doc_names=frozenset(load_corpus(corpus_dir)),
    )
    return build_app(state, static_dir=static_dir)
