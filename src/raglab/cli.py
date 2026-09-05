"""raglab CLI: `providers check`, `gold validate`, `index`, `search`, `eval run`."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from pathlib import Path

import typer
from dotenv import load_dotenv

from .config import RagLabConfig
from .corpus import load_corpus
from .evals.goldset import CorpusMismatchError, GoldSet, GoldSetError, load_gold_set, verify_corpus_hashes
from .evals.judge import Judge
from .evals.locations import CharSpan, line_of_offset, resolve_gold_locations
from .evals.metrics import compute_aggregates
from .evals.report import (
    GoldSetRef,
    Report,
    ReportWriter,
    RoleReportConfig,
    RunConfig,
    compute_delta,
    find_matching_prior_report,
    make_run_id,
)
from .evals.runner import EvalRunner
from .index.builder import IndexBuilder
from .index.store import EmbeddingMismatchError, NumpyStore
from .parsers.registry import ExtractedDocument, ParserError, extract_document
from .pipelines.retrieval import RetrievalPipeline
from .pipelines.whole_doc import WholeDocPipeline
from .providers.base import Message, ProviderAuthError
from .providers.registry import PROVIDER_PRECEDENCE, build_provider
from .retrieval.retriever import Retriever

load_dotenv()  # loads .env into the environment before any provider reads a key

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
DEFAULT_CONFIG_PATH = Path("config.toml")
PROBE_MODEL_ALIAS = "claude-sonnet-5"
SEARCH_PREVIEW_CHARS = 240

KNOWN_PIPELINES = ("whole_doc", "retrieval")


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


def _extract_referenced_documents(gold: GoldSet, documents: dict) -> dict[str, ExtractedDocument]:
    extracted: dict[str, ExtractedDocument] = {}
    for doc_name in sorted({entry.doc for entry in gold.entries}):
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


def _check_gold_locations(gold: GoldSet, extracted: dict[str, ExtractedDocument]) -> dict[str, list[CharSpan]]:
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
) -> dict[str, list[CharSpan]]:
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
) -> None:
    """Validate a gold set's schema, corpus hashes, and answer_location spans. Makes no model call."""
    gold, documents = _load_verified_gold_set(gold_path, corpus_dir)
    extracted = _extract_referenced_documents(gold, documents)
    _check_gold_locations(gold, extracted)
    typer.echo(f"OK: {len(gold.entries)} entries, {len(gold.corpus_hashes)} corpus documents verified.")


@app.command("index")
def index_build(
    corpus_dir: Path = typer.Option(DEFAULT_CORPUS_DIR, "--corpus-dir"),
    index_dir: Path = typer.Option(DEFAULT_INDEX_DIR, "--index-dir"),
) -> None:
    """Parse, chunk, and embed every corpus document into a persistent index.

    Only documents whose source hash or parser identity changed are re-chunked
    and re-embedded; the rest carry over untouched. Makes no model call
    (fastembed downloads its ONNX model once on first use, then runs locally).
    """
    documents = load_corpus(corpus_dir)
    if not documents:
        typer.echo(f"No documents found in {corpus_dir}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Indexing {len(documents)} document(s) from {corpus_dir}...")
    builder = IndexBuilder(NumpyStore(index_dir))
    results = builder.build(documents)

    failed = 0
    for result in results:
        if result.error:
            failed += 1
            typer.echo(f"  {result.doc}: FAILED ({result.error})")
        else:
            typer.echo(f"  {result.doc}: {result.chunk_count} chunks")

    typer.echo(f"Wrote index to {index_dir}")
    if failed:
        typer.echo(f"{failed} document(s) failed to index.", err=True)
        raise typer.Exit(code=1)


@app.command("search")
def search(
    query: str = typer.Argument(..., help="Search query"),
    k: int = typer.Option(5, "--k"),
    index_dir: Path = typer.Option(DEFAULT_INDEX_DIR, "--index-dir"),
    corpus_dir: Path = typer.Option(DEFAULT_CORPUS_DIR, "--corpus-dir"),
) -> None:
    """Search the index; print top-k chunks with score, document, line range, text."""
    store = NumpyStore(index_dir)
    if not store.exists():
        typer.echo(f"No index at {index_dir}. Run `raglab index` first.", err=True)
        raise typer.Exit(code=1)

    try:
        results = Retriever(store).search(query, k=k)
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
    corpus_dir: Path = typer.Option(DEFAULT_CORPUS_DIR, "--corpus-dir"),
    runs_dir: Path = typer.Option(DEFAULT_RUNS_DIR, "--runs-dir"),
    index_dir: Path = typer.Option(DEFAULT_INDEX_DIR, "--index-dir"),
    config_path: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config"),
) -> None:
    """Run every gold-set entry through a pipeline and provider; emit one report."""
    if pipeline_name not in KNOWN_PIPELINES:
        typer.echo(f"Unknown pipeline {pipeline_name!r}; known: {list(KNOWN_PIPELINES)}", err=True)
        raise typer.Exit(code=1)

    gold, documents = _load_verified_gold_set(gold_path, corpus_dir)
    extracted = _extract_referenced_documents(gold, documents)
    gold_spans = _resolve_gold_locations_for_run(gold, extracted)

    config = RagLabConfig.load(config_path)

    try:
        answer_provider = build_provider(config.answer.provider, config.answer.model)
        judge_provider = build_provider(config.judge.provider, config.judge.model)
    except ProviderAuthError as exc:
        typer.echo(f"Provider unavailable: {exc}", err=True)
        raise typer.Exit(code=1) from None

    chunk_spans: dict[str, CharSpan] = {}
    if pipeline_name == "retrieval":
        store = NumpyStore(index_dir)
        if not store.exists():
            typer.echo(f"No index at {index_dir}. Run `raglab index` first.", err=True)
            raise typer.Exit(code=1)

        manifest = store.load_manifest()
        referenced_docs = {entry.doc for entry in gold.entries}
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

        pipeline = RetrievalPipeline(
            answer_provider,
            Retriever(store),
            top_k=config.retrieval.top_k,
            score_threshold=config.retrieval.score_threshold,
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
    )

    run_config = RunConfig(
        pipeline=pipeline_name,
        answer=RoleReportConfig(provider=answer_provider.name, model=answer_provider.model),
        judge=RoleReportConfig(provider=judge_provider.name, model=judge_provider.model),
        concurrency=config.concurrency,
    )
    # Look for a matching-config prior report before writing this run's own.
    previous_report = find_matching_prior_report(runs_dir, run_config)

    started_at = datetime.now(timezone.utc)
    typer.echo(
        f"Running {len(gold.entries)} entries via {answer_provider.name}/{answer_provider.model} "
        f"(judge: {judge_provider.name}/{judge_provider.model})..."
    )

    start_perf = time.perf_counter()
    run_result = asyncio.run(runner.run())
    duration_s = time.perf_counter() - start_perf

    entries = run_result.entries
    aggregates = compute_aggregates(entries, run_result.reciprocal_ranks)
    report = Report(
        run_id=make_run_id(name, started_at),
        started_at=started_at.isoformat(),
        duration_s=duration_s,
        config=run_config,
        gold_set=GoldSetRef(path=str(gold_path), version=gold.version, entry_count=len(gold.entries)),
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
    typer.echo(
        f"input_tokens={aggregates.input_tokens} output_tokens={aggregates.output_tokens} "
        f"p50_latency_s={aggregates.p50_latency_s:.2f}"
    )

    failed = [
        e.id
        for e in entries
        if e.status == "errored" or (e.status == "graded" and e.verdict in ("not_grounded", "refused_incorrectly"))
    ]
    if failed:
        typer.echo(f"Failed entries: {', '.join(failed)}")

    if previous_report is not None:
        _print_delta(previous_report, report)


if __name__ == "__main__":
    app()
