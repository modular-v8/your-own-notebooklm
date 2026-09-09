"""FastAPI app: transport only, no answering logic. Wires the existing
`raglab` modules (config, retriever, pipelines) into HTTP routes and,
optionally, mounts the built frontend as static files.

`build_app(state)` takes already-constructed dependencies so tests can
inject fakes without a real provider, credential, or index (AGENTS.md: the
suite must pass with no network access and no API keys). `create_app(...)`
is the real wiring `raglab serve` uses.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from ..config import DEFAULT_CONFIG_PATH, RagLabConfig
from ..corpus import load_corpus
from ..experiments import DEFAULT_EXPERIMENTS_PATH, load_experiments
from ..index.store import NumpyStore, StoredChunk
from ..parsers.registry import extract_document
from ..pipelines.agentic import AgenticPipeline
from ..pipelines.retrieval import RetrievalPipeline
from ..providers.base import LLMProvider
from ..providers.registry import build_provider
from ..retrieval.retriever import Retriever
from . import routes_chunks, routes_collections, routes_conversations
from .store import DEFAULT_CONVERSATIONS_DIR, ConversationStore

DEFAULT_CORPUS_DIR = Path("evals/corpus")
DEFAULT_INDEX_DIR = Path("evals/index/fixed-900-150")
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


def build_app(state: AppState, *, static_dir: Path | None = None) -> FastAPI:
    app = FastAPI(title="raglab")
    app.state.raglab = state

    app.include_router(routes_collections.router)
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
    conversations_dir: Path = DEFAULT_CONVERSATIONS_DIR,
    experiments_path: Path = DEFAULT_EXPERIMENTS_PATH,
    static_dir: Path | None = DEFAULT_STATIC_DIR,
) -> FastAPI:
    config = RagLabConfig.load(config_path)

    store = NumpyStore(index_dir)
    if not store.exists():
        raise RuntimeError(f"No index at {index_dir}. Run `raglab index` first.")
    retriever = Retriever(store)

    documents = load_corpus(corpus_dir)
    doc_texts = {name: extract_document(doc).text for name, doc in documents.items()}

    provider = build_provider(config.answer.provider, config.answer.model)
    baseline_pipeline, agentic_pipeline = _build_pipelines(provider, retriever, config, experiments_path)

    state = AppState(
        config=config,
        conversation_store=ConversationStore(conversations_dir),
        baseline_pipeline=baseline_pipeline,
        agentic_pipeline=agentic_pipeline,
        chunks_by_id={chunk.chunk_id: chunk for chunk in store.load_chunks()},
        doc_texts=doc_texts,
    )
    return build_app(state, static_dir=static_dir)
