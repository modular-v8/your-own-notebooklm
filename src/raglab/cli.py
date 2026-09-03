"""raglab CLI: `providers check`, `gold validate`, `eval run`."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from pathlib import Path

import typer
from dotenv import load_dotenv

from .config import RagLabConfig
from .corpus import load_corpus
from .evals.goldset import CorpusMismatchError, GoldSetError, load_gold_set, verify_corpus_hashes
from .evals.judge import Judge
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
from .pipelines.whole_doc import WholeDocPipeline
from .providers.base import Message, ProviderAuthError
from .providers.registry import PROVIDER_PRECEDENCE, build_provider

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
DEFAULT_CONFIG_PATH = Path("config.toml")
PROBE_MODEL_ALIAS = "claude-sonnet-5"

PIPELINES = {"whole_doc": WholeDocPipeline}


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


@gold_app.command("validate")
def gold_validate(
    gold_path: Path = typer.Argument(..., help="Path to the gold-set YAML file"),
    corpus_dir: Path = typer.Option(DEFAULT_CORPUS_DIR, help="Directory of corpus documents"),
) -> None:
    """Validate a gold set's schema and its corpus hashes. Makes no model call."""
    gold, _ = _load_verified_gold_set(gold_path, corpus_dir)
    typer.echo(f"OK: {len(gold.entries)} entries, {len(gold.corpus_hashes)} corpus documents verified.")


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
    config_path: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config"),
) -> None:
    """Run every gold-set entry through a pipeline and provider; emit one report."""
    if pipeline_name not in PIPELINES:
        typer.echo(f"Unknown pipeline {pipeline_name!r}; known: {sorted(PIPELINES)}", err=True)
        raise typer.Exit(code=1)

    gold, documents = _load_verified_gold_set(gold_path, corpus_dir)
    config = RagLabConfig.load(config_path)

    try:
        answer_provider = build_provider(config.answer.provider, config.answer.model)
        judge_provider = build_provider(config.judge.provider, config.judge.model)
    except ProviderAuthError as exc:
        typer.echo(f"Provider unavailable: {exc}", err=True)
        raise typer.Exit(code=1) from None

    pipeline = PIPELINES[pipeline_name](answer_provider)
    judge = Judge(judge_provider)
    runner = EvalRunner(pipeline, judge, gold, documents, concurrency=config.concurrency)

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
    entries = asyncio.run(runner.run())
    duration_s = time.perf_counter() - start_perf

    aggregates = compute_aggregates(entries)
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
