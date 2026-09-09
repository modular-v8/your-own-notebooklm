"""raglab CLI: `providers check`, `gold validate`, `index`, `search`, `eval run`."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from pathlib import Path

import typer
from dotenv import load_dotenv

from .collections import UnknownCollectionError, require_collection, unreachable_documents
from .config import RagLabConfig
from .corpus import load_corpus
from .evals.compare import CompareError, compare_reports
from .evals.goldset import (
    CollectionMembershipError,
    CorpusMismatchError,
    GoldSet,
    GoldSetError,
    check_tag_vocabulary,
    load_gold_set,
    verify_collection_membership,
    verify_corpus_hashes,
)
from .evals.judge import Judge
from .evals.locations import CharSpan, GoldSpan, find_matches, line_of_offset, resolve_gold_locations
from .evals.metrics import compute_aggregates, find_disagreements
from .evals.report import (
    GoldSetRef,
    Report,
    ReportWriter,
    RoleReportConfig,
    RunConfig,
    compute_delta,
    entry_ids_fingerprint,
    find_matching_prior_report,
    make_run_id,
)
from .evals.runner import EvalRunner
from .evals.validate import check_not_in_document_lexical_matches
from .experiments import DEFAULT_EXPERIMENTS_PATH, ExperimentsError, index_subdir_name, load_experiments
from .index.builder import ChunkingMismatchError, IndexBuilder
from .index.store import ChunkerSettings, EmbeddingMismatchError, NumpyStore
from .parsers.registry import ExtractedDocument, ParserError, extract_document
from .pipelines.agentic import DEFAULT_MAX_CALLS, AgenticPipeline
from .pipelines.retrieval import RetrievalPipeline
from .pipelines.whole_doc import WholeDocPipeline
from .providers.base import Message, ProviderAuthError
from .providers.registry import PROVIDER_PRECEDENCE, build_provider
from .retrieval.fusion import DEFAULT_RRF_K
from .retrieval.reranker import DEFAULT_RERANKER_MODEL, Reranker
from .retrieval.retriever import Retriever
from .retrieval.rewriter import QueryRewriter

load_dotenv()  # loads .env into the environment before any provider reads a key

DEFAULT_CONVERSATIONS_DIR = Path("conversations")
DEFAULT_STATIC_DIR = Path("web/dist")
SERVE_HOST = "127.0.0.1"  # localhost only, per spec -- never configurable

app = typer.Typer(no_args_is_help=True)
providers_app = typer.Typer(no_args_is_help=True)
gold_app = typer.Typer(no_args_is_help=True)
eval_app = typer.Typer(no_args_is_help=True)
app.add_typer(providers_app, name="providers")
app.add_typer(gold_app, name="gold")
app.add_typer(eval_app, name="eval")

DEFAULT_CORPUS_DIR = Path("evals/corpus")
DEFAULT_RUNS_DIR = Path("evals/runs")
DEFAULT_INDEX_DIR = Path("evals/index")
# `index_subdir_name` for the baseline (fixed/900/150) chunking config --
# hardcoded rather than computed so `search`/`collections` (neither
# --experiment-aware) don't need an ExperimentConfig just to find the one
# index they've ever used. `index`/`eval run` derive this dynamically instead.
DEFAULT_FIXED_INDEX_DIR = DEFAULT_INDEX_DIR / "fixed-900-150"
DEFAULT_CONFIG_PATH = Path("config.toml")
PROBE_MODEL_ALIAS = "claude-sonnet-5"
SEARCH_PREVIEW_CHARS = 240

KNOWN_PIPELINES = ("whole_doc", "retrieval", "agentic")


@providers_app.command("check")
def providers_check() -> None:
    """Authenticate against all three providers; print each resolved model id.

    Makes one small, real, metered call per provider that has a credential.
    """
    typer.echo("Checking providers (each check below makes one small live model call)...")
    for name in PROVIDER_PRECEDENCE:
        try:
            provider = build_provider(name, PROBE_MODEL_ALIAS)
        except ProviderAuthError as exc:
            typer.echo(f"  {name}: not configured ({exc})")
            continue

        try:
            count = asyncio.run(provider.count_tokens([Message(role="user", content="ping")]))
            typer.echo(
                f"  {name}: OK, model={provider.model}, "
                f"context_window={provider.context_window} (probe: {count} tokens)"
            )
        except ProviderAuthError as exc:
            typer.echo(f"  {name}: auth failed ({exc})")
        except Exception as exc:  # noqa: BLE001 - surfacing any failure here is the point of this command
            typer.echo(f"  {name}: error ({exc})")


def _load_verified_gold_set(gold_path: Path, corpus_dir: Path):
    """Validate schema + corpus hashes; print problems and exit(1) on failure."""
    try:
        gold = load_gold_set(gold_path)
    except GoldSetError as exc:
        typer.echo(f"Gold set schema invalid ({len(exc.messages)} problem(s)):", err=True)
        for message in exc.messages:
            typer.echo(f"  - {message}", err=True)
        raise typer.Exit(code=1) from None

    documents = load_corpus(corpus_dir)
    try:
        verify_corpus_hashes(gold, documents)
    except CorpusMismatchError as exc:
        typer.echo(f"Corpus hash mismatch ({len(exc.messages)} problem(s)):", err=True)
        for message in exc.messages:
            typer.echo(f"  - {message}", err=True)
        raise typer.Exit(code=1) from None

    return gold, documents


def _extract_documents(gold: GoldSet, documents: dict, doc_names: set[str]) -> dict[str, ExtractedDocument]:
    extracted: dict[str, ExtractedDocument] = {}
    for doc_name in sorted(doc_names):
        document = documents.get(doc_name)
        if document is None:
            typer.echo(f"Corpus missing document {doc_name!r} referenced by gold set", err=True)
            raise typer.Exit(code=1)
        try:
            extracted[doc_name] = extract_document(document)
        except ParserError as exc:
            typer.echo(f"Parser failed on {doc_name}: {exc}", err=True)
            raise typer.Exit(code=1) from None
    return extracted


def _extract_referenced_documents(gold: GoldSet, documents: dict) -> dict[str, ExtractedDocument]:
    return _extract_documents(gold, documents, {doc for entry in gold.entries for doc in entry.docs})


def _extract_corpus_documents(gold: GoldSet, documents: dict) -> dict[str, ExtractedDocument]:
    """Every document the gold set's corpus_hashes names, not just the ones
    entries cite -- a not-in-document entry names no doc of its own, so
    checking its claim against the corpus means checking all of it."""
    return _extract_documents(gold, documents, set(gold.corpus_hashes))


def _check_collection(gold: GoldSet, config: RagLabConfig) -> None:
    try:
        verify_collection_membership(gold, config.collections)
    except CollectionMembershipError as exc:
        typer.echo(f"Collection membership invalid ({len(exc.messages)} problem(s)):", err=True)
        for message in exc.messages:
            typer.echo(f"  - {message}", err=True)
        raise typer.Exit(code=1) from None


def _check_gold_locations(gold: GoldSet, extracted: dict[str, ExtractedDocument]) -> dict[str, list[GoldSpan]]:
    """Strict: used by `gold validate`, a dedicated gold-set linting command."""
    gold_spans, errors = resolve_gold_locations(gold, extracted)
    if errors:
        typer.echo(f"Unscoreable gold entries ({len(errors)}):", err=True)
        for message in errors:
            typer.echo(f"  - {message}", err=True)
        raise typer.Exit(code=1)
    return gold_spans


def _resolve_gold_locations_for_run(
    gold: GoldSet, extracted: dict[str, ExtractedDocument]
) -> dict[str, list[GoldSpan]]:
    """Lenient: used by `eval run`. An unresolvable location makes that one
    entry unscoreable for recall/MRR (reported, before any model call) but
    doesn't block answering and grading the rest of the gold set — the
    entry's `expected_answer` is still valid groundedness ground truth even
    when its location can't be pinned to a unique span (e.g. a rule id that
    also appears in the document's own revision history)."""
    gold_spans, errors = resolve_gold_locations(gold, extracted)
    if errors:
        typer.echo(f"Unscoreable for recall ({len(errors)} entr{'y' if len(errors) == 1 else 'ies'}, excluded from recall/MRR only):")
        for message in errors:
            typer.echo(f"  - {message}")
    return gold_spans


@gold_app.command("validate")
def gold_validate(
    gold_path: Path = typer.Argument(..., help="Path to the gold-set YAML file"),
    corpus_dir: Path = typer.Option(DEFAULT_CORPUS_DIR, help="Directory of corpus documents"),
    config_path: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config"),
) -> None:
    """Validate a gold set's schema, corpus hashes, collection membership,
    and answer_location spans. Makes no model call."""
    gold, documents = _load_verified_gold_set(gold_path, corpus_dir)
    config = RagLabConfig.load(config_path)
    _check_collection(gold, config)

    extracted = _extract_referenced_documents(gold, documents)
    _check_gold_locations(gold, extracted)

    tag_warnings = check_tag_vocabulary(gold)
    for warning in tag_warnings:
        typer.echo(f"Warning: {warning}")

    corpus_extracted = _extract_corpus_documents(gold, documents)
    for warning in check_not_in_document_lexical_matches(gold, corpus_extracted):
        typer.echo(f"Warning: {warning}")

    typer.echo(f"OK: {len(gold.entries)} entries, {len(gold.corpus_hashes)} corpus documents verified.")


@gold_app.command("locate")
def gold_locate(
    anchor: str = typer.Argument(..., help="Anchor text to search for (rule id, heading, etc.)"),
    doc: str | None = typer.Option(None, "--doc", help="Restrict the search to one corpus document"),
    corpus_dir: Path = typer.Option(DEFAULT_CORPUS_DIR, help="Directory of corpus documents"),
) -> None:
    """Print every match of an anchor with its line number, marking which
    (if any) begins a line — the same boundary rule `section` anchors use.
    Makes no model call."""
    documents = load_corpus(corpus_dir)
    doc_names = [doc] if doc else sorted(documents)

    total_matches = 0
    for doc_name in doc_names:
        document = documents.get(doc_name)
        if document is None:
            typer.echo(f"{doc_name}: not found in {corpus_dir}", err=True)
            raise typer.Exit(code=1)
        try:
            extracted = extract_document(document)
        except ParserError as exc:
            typer.echo(f"{doc_name}: parser failed ({exc})", err=True)
            continue

        matches = find_matches(extracted.text, anchor)
        if not matches:
            continue
        typer.echo(f"{doc_name}:")
        for match in matches:
            marker = "line-initial" if match.line_initial else "mid-sentence"
            if match.cross_reference:
                marker += ", cross-reference"
            typer.echo(f"  line {match.line} [{marker}]: {match.snippet}")
        total_matches += len(matches)

    if total_matches == 0:
        typer.echo(f"No matches for {anchor!r}.")


@app.command("index")
def index_build(
    corpus_dir: Path = typer.Option(DEFAULT_CORPUS_DIR, "--corpus-dir"),
    index_dir: Path | None = typer.Option(
        None, "--index-dir", help="Defaults to evals/index/<strategy>, derived from --experiment"
    ),
    experiment_name: str = typer.Option(
        "baseline", "--experiment", help="Named ExperimentConfig from experiments.toml (selects chunking strategy)"
    ),
    config_path: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config"),
    experiments_path: Path = typer.Option(DEFAULT_EXPERIMENTS_PATH, "--experiments"),
) -> None:
    """Parse, chunk, and embed every corpus document into a persistent index.

    Only documents whose source hash or parser identity changed are re-chunked
    and re-embedded; the rest carry over untouched (a collection reassignment
    alone never triggers a re-embed). Makes no model call (fastembed downloads
    its ONNX model once on first use, then runs locally).

    Each chunking strategy gets its own index directory (evals/index/<strategy>/
    by default) -- building into a directory whose existing index used a
    different chunking config is refused rather than silently mixed.
    """
    documents = load_corpus(corpus_dir)
    if not documents:
        typer.echo(f"No documents found in {corpus_dir}", err=True)
        raise typer.Exit(code=1)

    try:
        experiments = load_experiments(experiments_path)
    except ExperimentsError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from None
    if experiment_name not in experiments:
        typer.echo(f"Unknown experiment {experiment_name!r}; known: {sorted(experiments)}", err=True)
        raise typer.Exit(code=1)
    chunking = experiments[experiment_name].chunking
    effective_index_dir = index_dir if index_dir is not None else DEFAULT_INDEX_DIR / index_subdir_name(chunking)

    config = RagLabConfig.load(config_path)

    typer.echo(f"Indexing {len(documents)} document(s) from {corpus_dir} ({chunking.strategy} chunking)...")
    chunker_settings = ChunkerSettings(strategy=chunking.strategy, size=chunking.size, overlap=chunking.overlap)
    builder = IndexBuilder(NumpyStore(effective_index_dir), chunking=chunker_settings)
    try:
        results = builder.build(documents, collections=config.collections)
    except ChunkingMismatchError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from None

    failed = 0
    for result in results:
        if result.error:
            failed += 1
            typer.echo(f"  {result.doc}: FAILED ({result.error})")
        else:
            typer.echo(f"  {result.doc}: {result.chunk_count} chunks")

    typer.echo(f"Wrote index to {effective_index_dir}")

    for doc_name in unreachable_documents(list(documents), config.collections):
        typer.echo(f"Warning: {doc_name} belongs to no collection; unreachable by any scoped query.")

    if failed:
        typer.echo(f"{failed} document(s) failed to index.", err=True)
        raise typer.Exit(code=1)


@app.command("collections")
def collections_list(
    index_dir: Path = typer.Option(DEFAULT_FIXED_INDEX_DIR, "--index-dir"),
    config_path: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config"),
) -> None:
    """List each configured collection with its documents and chunk counts."""
    config = RagLabConfig.load(config_path)
    if not config.collections:
        typer.echo("No collections configured in config.toml.")
        return

    store = NumpyStore(index_dir)
    chunk_counts: dict[str, int] = {}
    if store.exists():
        for chunk in store.load_chunks():
            for name in chunk.collections:
                chunk_counts[name] = chunk_counts.get(name, 0) + 1
    else:
        typer.echo(f"No index at {index_dir}; showing configured membership only (chunk counts unavailable).")

    for name, docs in config.collections.items():
        typer.echo(f"{name}: {len(docs)} document(s), {chunk_counts.get(name, 0)} chunk(s)")
        for doc in docs:
            typer.echo(f"  - {doc}")


@app.command("serve")
def serve(
    port: int = typer.Option(8000, "--port"),
    config_path: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config"),
    corpus_dir: Path = typer.Option(DEFAULT_CORPUS_DIR, "--corpus-dir"),
    index_dir: Path = typer.Option(DEFAULT_FIXED_INDEX_DIR, "--index-dir"),
    conversations_dir: Path = typer.Option(DEFAULT_CONVERSATIONS_DIR, "--conversations-dir"),
    experiments_path: Path = typer.Option(DEFAULT_EXPERIMENTS_PATH, "--experiments"),
    static_dir: Path = typer.Option(DEFAULT_STATIC_DIR, "--static-dir", help="Built frontend (web/dist); skipped if absent"),
) -> None:
    """Serve the backend and the built frontend on localhost. Never binds
    an external interface (spec: local-first, single-user)."""
    import uvicorn

    from .api.app import create_app

    try:
        asgi_app = create_app(
            config_path=config_path,
            corpus_dir=corpus_dir,
            index_dir=index_dir,
            conversations_dir=conversations_dir,
            experiments_path=experiments_path,
            static_dir=static_dir,
        )
    except (ProviderAuthError, RuntimeError) as exc:
        typer.echo(f"Cannot start server: {exc}", err=True)
        raise typer.Exit(code=1) from None

    typer.echo(f"Serving on http://{SERVE_HOST}:{port} (localhost only)")
    uvicorn.run(asgi_app, host=SERVE_HOST, port=port)


@app.command("search")
def search(
    query: str = typer.Argument(..., help="Search query"),
    k: int = typer.Option(5, "--k"),
    collection: str | None = typer.Option(None, "--collection", help="Restrict search to this collection"),
    index_dir: Path = typer.Option(DEFAULT_FIXED_INDEX_DIR, "--index-dir"),
    corpus_dir: Path = typer.Option(DEFAULT_CORPUS_DIR, "--corpus-dir"),
    config_path: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config"),
) -> None:
    """Search the index; print top-k chunks with score, document, line range, text."""
    store = NumpyStore(index_dir)
    if not store.exists():
        typer.echo(f"No index at {index_dir}. Run `raglab index` first.", err=True)
        raise typer.Exit(code=1)

    if collection is not None:
        config = RagLabConfig.load(config_path)
        try:
            require_collection(collection, config.collections)
        except UnknownCollectionError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from None

    try:
        results = Retriever(store).search(query, k=k, collection=collection)
    except EmbeddingMismatchError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from None

    if not results:
        typer.echo("No results.")
        return

    documents = load_corpus(corpus_dir)
    text_cache: dict[str, str] = {}

    for i, result in enumerate(results, start=1):
        if result.doc not in text_cache and result.doc in documents:
            try:
                text_cache[result.doc] = extract_document(documents[result.doc]).text
            except ParserError:
                text_cache[result.doc] = ""
        doc_text = text_cache.get(result.doc, "")

        if doc_text:
            line_start = line_of_offset(doc_text, result.char_start)
            line_end = line_of_offset(doc_text, max(result.char_start, result.char_end - 1))
            line_range = f"{line_start}-{line_end}"
        else:
            line_range = "?"

        preview = " ".join(result.text.split())
        if len(preview) > SEARCH_PREVIEW_CHARS:
            preview = preview[:SEARCH_PREVIEW_CHARS] + "…"

        typer.echo(f"{i}. [{result.score:.3f}] {result.doc}:{line_range} ({result.chunk_id})")
        typer.echo(f"   {preview}")


def _fmt_pct(value: float | None) -> str:
    return f"{value:.2%}" if value is not None else "n/a"


def _print_delta(previous: Report, current: Report) -> None:
    delta = compute_delta(previous, current)
    typer.echo(f"Delta vs {previous.run_id}:")
    for metric, value in delta.items():
        typer.echo(f"  {metric}: {value:+.4f}" if value is not None else f"  {metric}: n/a")


@eval_app.command("run")
def eval_run(
    gold_path: Path = typer.Option(..., "--gold", help="Path to the gold-set YAML file"),
    name: str = typer.Option(..., "--name", help="Short run name, used in the report filename"),
    pipeline_name: str = typer.Option("whole_doc", "--pipeline"),
    collection: str | None = typer.Option(
        None, "--collection", help="Override the gold set's own collection for this run"
    ),
    experiment_name: str = typer.Option(
        "baseline", "--experiment", help="Named ExperimentConfig from experiments.toml"
    ),
    corpus_dir: Path = typer.Option(DEFAULT_CORPUS_DIR, "--corpus-dir"),
    runs_dir: Path = typer.Option(DEFAULT_RUNS_DIR, "--runs-dir"),
    index_dir: Path | None = typer.Option(
        None, "--index-dir", help="Defaults to evals/index/<strategy>, derived from --experiment"
    ),
    config_path: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config"),
    experiments_path: Path = typer.Option(DEFAULT_EXPERIMENTS_PATH, "--experiments"),
) -> None:
    """Run every gold-set entry through a pipeline and provider; emit one report."""
    if pipeline_name not in KNOWN_PIPELINES:
        typer.echo(f"Unknown pipeline {pipeline_name!r}; known: {list(KNOWN_PIPELINES)}", err=True)
        raise typer.Exit(code=1)

    try:
        experiments = load_experiments(experiments_path)
    except ExperimentsError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from None
    if experiment_name not in experiments:
        typer.echo(f"Unknown experiment {experiment_name!r}; known: {sorted(experiments)}", err=True)
        raise typer.Exit(code=1)
    experiment = experiments[experiment_name]
    effective_index_dir = index_dir if index_dir is not None else DEFAULT_INDEX_DIR / index_subdir_name(experiment.chunking)

    gold, documents = _load_verified_gold_set(gold_path, corpus_dir)
    config = RagLabConfig.load(config_path)
    # Membership validation always checks the gold set's own declared home
    # collection -- that's independent of which collection this particular
    # run is scoped to.
    _check_collection(gold, config)
    active_collection = collection or gold.collection
    try:
        require_collection(active_collection, config.collections)
    except UnknownCollectionError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from None

    extracted = _extract_referenced_documents(gold, documents)
    gold_spans = _resolve_gold_locations_for_run(gold, extracted)

    try:
        answer_provider = build_provider(config.answer.provider, config.answer.model)
        judge_provider = build_provider(config.judge.provider, config.judge.model)
    except ProviderAuthError as exc:
        typer.echo(f"Provider unavailable: {exc}", err=True)
        raise typer.Exit(code=1) from None

    chunk_spans: dict[str, CharSpan] = {}
    if pipeline_name in ("retrieval", "agentic"):
        store = NumpyStore(effective_index_dir)
        if not store.exists():
            typer.echo(f"No index at {effective_index_dir}. Run `raglab index` first.", err=True)
            raise typer.Exit(code=1)

        manifest = store.load_manifest()
        if manifest.chunker.strategy != experiment.chunking.strategy:
            typer.echo(
                f"Index at {effective_index_dir} was built with {manifest.chunker.strategy!r} chunking, "
                f"but experiment {experiment.name!r} requests {experiment.chunking.strategy!r}. "
                "Run `raglab index --experiment ...` for this experiment first.",
                err=True,
            )
            raise typer.Exit(code=1)

        referenced_docs = {doc for entry in gold.entries for doc in entry.docs}
        missing = sorted(referenced_docs - set(manifest.documents))
        if missing:
            typer.echo(f"Index missing document(s): {', '.join(missing)}. Run `raglab index`.", err=True)
            raise typer.Exit(code=1)

        stale = sorted(
            doc_name
            for doc_name in referenced_docs
            if manifest.documents[doc_name].source_sha256 != extracted[doc_name].document.sha256
            or manifest.documents[doc_name].parser != str(extracted[doc_name].parser)
        )
        if stale:
            typer.echo(f"Index stale for: {', '.join(stale)}. Re-run `raglab index`.", err=True)
            raise typer.Exit(code=1)

        if pipeline_name == "agentic":
            max_calls = experiment.agentic.max_calls if experiment.agentic is not None else DEFAULT_MAX_CALLS
            prune_top_n = experiment.agentic.prune_top_n if experiment.agentic is not None else None
            tight_citations = experiment.agentic.tight_citations if experiment.agentic is not None else False
            pipeline = AgenticPipeline(
                answer_provider,
                Retriever(store),
                top_k=experiment.retrieval.k,
                max_calls=max_calls,
                prune_top_n=prune_top_n,
                tight_citations=tight_citations,
            )
        else:
            reranker = None
            if experiment.reranking is not None and experiment.reranking.mode != "off":
                if experiment.reranking.mode == "llm":
                    typer.echo(
                        "Experiment {!r} requests an LLM reranker, which is not built (T2.6's ONNX "
                        "cross-encoder is unblocked and used instead for every reranking experiment "
                        "so far).".format(experiment.name),
                        err=True,
                    )
                    raise typer.Exit(code=1)
                reranker = Reranker(model_name=experiment.reranking.model or DEFAULT_RERANKER_MODEL)

            rewriter = None
            if experiment.rewriting is not None and experiment.rewriting.mode != "off":
                if experiment.rewriting.mode != "follow_ups_only":
                    typer.echo(
                        f"Experiment {experiment.name!r} requests rewriting mode "
                        f"{experiment.rewriting.mode!r}, which isn't built yet (only 'follow_ups_only' is).",
                        err=True,
                    )
                    raise typer.Exit(code=1)
                rewriter = QueryRewriter(answer_provider)

            pipeline = RetrievalPipeline(
                answer_provider,
                Retriever(store),
                top_k=experiment.retrieval.k,
                score_threshold=config.retrieval.score_threshold,
                mode=experiment.retrieval.mode,
                candidate_k=experiment.retrieval.candidate_k,
                rrf_k=experiment.retrieval.rrf_k or DEFAULT_RRF_K,
                reranker=reranker,
                rewriter=rewriter,
            )
        chunk_spans = {chunk.chunk_id: (chunk.char_start, chunk.char_end) for chunk in store.load_chunks()}
    else:
        pipeline = WholeDocPipeline(answer_provider, {doc_name: ed.text for doc_name, ed in extracted.items()})

    judge = Judge(judge_provider)
    runner = EvalRunner(
        pipeline,
        judge,
        gold,
        concurrency=config.concurrency,
        gold_spans=gold_spans,
        chunk_spans=chunk_spans,
        collection=active_collection,
        collections=config.collections,
    )

    run_config = RunConfig(
        pipeline=pipeline_name,
        collection=active_collection,
        answer=RoleReportConfig(provider=answer_provider.name, model=answer_provider.model),
        judge=RoleReportConfig(provider=judge_provider.name, model=judge_provider.model),
        concurrency=config.concurrency,
        experiment=experiment,
    )
    gold_set_ref = GoldSetRef(
        path=str(gold_path),
        version=gold.version,
        entry_count=len(gold.entries),
        entry_ids_fingerprint=entry_ids_fingerprint([e.id for e in gold.entries]),
    )
    # Look for a matching-config, matching-gold-set prior report before
    # writing this run's own.
    previous_report = find_matching_prior_report(runs_dir, run_config, gold_set_ref)

    started_at = datetime.now(timezone.utc)
    typer.echo(
        f"Running {len(gold.entries)} entries via {answer_provider.name}/{answer_provider.model} "
        f"(judge: {judge_provider.name}/{judge_provider.model})..."
    )

    start_perf = time.perf_counter()
    run_result = asyncio.run(runner.run())
    duration_s = time.perf_counter() - start_perf

    entries = run_result.entries
    tags_by_id = {entry.id: entry.tags for entry in gold.entries}
    turn_position_by_id = {
        entry.id: ("follow_up" if entry.is_follow_up else "standalone") for entry in gold.entries
    }
    aggregates = compute_aggregates(entries, run_result.reciprocal_ranks, tags_by_id, turn_position_by_id)
    report = Report(
        run_id=make_run_id(name, started_at),
        started_at=started_at.isoformat(),
        duration_s=duration_s,
        config=run_config,
        gold_set=gold_set_ref,
        corpus_hashes=gold.corpus_hashes,
        aggregates=aggregates,
        entries=entries,
    )

    report_path = ReportWriter(runs_dir).write(report)

    typer.echo(f"Wrote {report_path}")
    typer.echo(
        f"graded={aggregates.graded} ungraded={aggregates.ungraded} "
        f"skipped={aggregates.skipped} errored={aggregates.errored}"
    )
    if aggregates.grounded_rate is not None:
        typer.echo(f"grounded_rate={aggregates.grounded_rate:.2%}")
    if aggregates.refusal_correct_rate is not None:
        typer.echo(f"refusal_correct_rate={aggregates.refusal_correct_rate:.2%}")
    if aggregates.recall_at_k is not None:
        typer.echo(f"recall_at_k={aggregates.recall_at_k:.2%} mrr={aggregates.mrr:.4f}")
    if aggregates.citation_precision is not None or aggregates.fabrication_rate is not None:
        typer.echo(
            f"citation_precision={_fmt_pct(aggregates.citation_precision)} "
            f"fabrication_rate={_fmt_pct(aggregates.fabrication_rate)} "
            f"mean_coverage={_fmt_pct(aggregates.mean_coverage)} uncited={aggregates.uncited}"
        )
    typer.echo(
        f"input_tokens={aggregates.input_tokens} output_tokens={aggregates.output_tokens} "
        f"p50_latency_s={aggregates.p50_latency_s:.2f}"
    )

    if aggregates.by_tag:
        typer.echo("By tag:")
        for tag, tag_agg in aggregates.by_tag.items():
            typer.echo(
                f"  {tag} (n={tag_agg.count}): grounded={_fmt_pct(tag_agg.grounded_rate)} "
                f"refusal_correct={_fmt_pct(tag_agg.refusal_correct_rate)} "
                f"recall_at_k={_fmt_pct(tag_agg.recall_at_k)} "
                f"citation_precision={_fmt_pct(tag_agg.citation_precision)} "
                f"fabrication_rate={_fmt_pct(tag_agg.fabrication_rate)} "
                f"mean_coverage={_fmt_pct(tag_agg.mean_coverage)}"
            )

    if aggregates.by_turn_position:
        typer.echo("By turn position:")
        for position, pos_agg in aggregates.by_turn_position.items():
            mean_tokens = f"{pos_agg.mean_input_tokens:.0f}" if pos_agg.mean_input_tokens is not None else "n/a"
            typer.echo(
                f"  {position} (n={pos_agg.count}): recall_at_k={_fmt_pct(pos_agg.recall_at_k)} "
                f"grounded={_fmt_pct(pos_agg.grounded_rate)} "
                f"mean_input_tokens={mean_tokens}"
            )

    failed = [
        e.id
        for e in entries
        if e.status == "errored" or (e.status == "graded" and e.verdict in ("not_grounded", "refused_incorrectly"))
    ]
    if failed:
        typer.echo(f"Failed entries: {', '.join(failed)}")

    disagreements = find_disagreements(entries)
    typer.echo(f"Disagreements (judge vs. deterministic citation check): {len(disagreements)}")
    for entry in disagreements:
        typer.echo(f"  {entry.id}: judge={entry.verdict} citation_precision={entry.citation_precision:.2f}")

    if previous_report is not None:
        _print_delta(previous_report, report)
    else:
        typer.echo("No comparable prior run found (matching config + gold set).")


@app.command("compare")
def compare_cmd(
    baseline_path: Path = typer.Argument(..., help="Baseline report JSON"),
    experiment_path: Path = typer.Argument(..., help="Experiment report JSON"),
) -> None:
    """Paired per-entry comparison of an experiment report against a baseline report."""
    try:
        baseline = Report.model_validate_json(baseline_path.read_text(encoding="utf-8"))
        experiment = Report.model_validate_json(experiment_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        typer.echo(f"Failed to load report: {exc}", err=True)
        raise typer.Exit(code=1) from None

    # Per-tag breakdown needs each entry's tags, which reports don't carry --
    # re-derived from the gold set both reports are guaranteed (post-guard)
    # to share. Best-effort: an unreadable gold set degrades to no tag
    # breakdown rather than blocking the comparison itself.
    tags_by_id: dict[str, list[str]] = {}
    try:
        gold = load_gold_set(Path(baseline.gold_set.path))
        tags_by_id = {entry.id: entry.tags for entry in gold.entries}
    except (OSError, GoldSetError):
        pass

    try:
        result = compare_reports(baseline, experiment, tags_by_id)
    except CompareError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from None

    total = result.wins + result.losses + result.ties
    typer.echo(f"{experiment.run_id} vs. {baseline.run_id}")
    typer.echo(
        f"wins={result.wins} losses={result.losses} ties={result.ties} excluded={len(result.excluded)}"
    )
    if total:
        typer.echo(
            f"win_rate={result.wins / total:.2%} loss_rate={result.losses / total:.2%} "
            f"tie_rate={result.ties / total:.2%}"
        )
    if result.chunking_note:
        typer.echo(result.chunking_note)

    if result.regressed:
        typer.echo("Regressed entries:")
        for entry in result.regressed:
            typer.echo(f"  {entry.id}: {', '.join(entry.regressed_metrics)}")

    if result.by_tag:
        typer.echo("By tag:")
        for tag, counts in result.by_tag.items():
            typer.echo(f"  {tag} (n={counts.count}): wins={counts.wins} losses={counts.losses} ties={counts.ties}")


if __name__ == "__main__":
    app()
