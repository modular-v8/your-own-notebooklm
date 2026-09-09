"""Run report schema, writer, and delta-vs-prior-matching-config reporting.

Retrieval-metric fields (`recall_at_k`, `mrr`, per-entry `retrieved` /
`recall_hit`) are already present here, left null. Phase 1 populates them
without a schema change — that stability is the point of building this before
the pipeline it measures.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from ..experiments import ExperimentConfig

EntryStatus = Literal["graded", "skipped", "ungraded", "errored"]

RUN_ID_TIMESTAMP_FORMAT = "%Y-%m-%dT%H-%M-%SZ"


class RoleReportConfig(BaseModel):
    provider: str
    model: str
    params: dict[str, Any] = {}


class RunConfig(BaseModel):
    pipeline: str
    # Default keeps pre-Phase-3 reports loadable; "" never matches a real
    # collection, so an old report simply never counts as comparable.
    collection: str = ""
    answer: RoleReportConfig
    judge: RoleReportConfig
    concurrency: int
    # Default keeps pre-Phase-4 reports loadable (spec: a report without a
    # recorded experiment config can't be used as a paired comparison
    # source -- None is exactly that "missing" state, not a stand-in baseline).
    experiment: ExperimentConfig | None = None


class GoldSetRef(BaseModel):
    path: str
    version: int
    entry_count: int
    # sha256 of the sorted entry ids -- lets delta-matching tell "same gold
    # set, run again" from "different gold set, same provider config"
    # (a Phase 0 defect: see specs/3-collections/plan.md). Default "" for
    # pre-Phase-3 reports, which then never match by construction.
    entry_ids_fingerprint: str = ""


def entry_ids_fingerprint(entry_ids: list[str]) -> str:
    return hashlib.sha256(",".join(sorted(entry_ids)).encode()).hexdigest()[:16]


class TagAggregates(BaseModel):
    """Same rates as Aggregates, computed over just the entries carrying
    one particular gold-set tag. mrr is a ranking metric, not a rate, and
    isn't broken down per-tag (see plan.md's data model)."""

    count: int
    grounded_rate: float | None = None
    refusal_correct_rate: float | None = None
    recall_at_k: float | None = None
    citation_precision: float | None = None
    fabrication_rate: float | None = None
    mean_coverage: float | None = None
    uncited: int = 0
    # Mean input tokens per question in this group -- the by_turn_position
    # breakdown is what shows what conversation history costs a follow-up.
    mean_input_tokens: float | None = None


class Aggregates(BaseModel):
    grounded_rate: float | None
    refusal_correct_rate: float | None
    graded: int
    ungraded: int
    skipped: int
    errored: int
    recall_at_k: float | None = None
    mrr: float | None = None
    input_tokens: int
    output_tokens: int
    p50_latency_s: float
    citation_precision: float | None = None
    fabrication_rate: float | None = None
    mean_coverage: float | None = None
    uncited: int = 0
    by_tag: dict[str, TagAggregates] = {}
    # Keyed "standalone" / "follow_up" -- same shape as by_tag (plan.md),
    # since a turn position is really just another grouping.
    by_turn_position: dict[str, TagAggregates] = {}


class UsageReport(BaseModel):
    input_tokens: int
    output_tokens: int
    # Cache-aware breakdown (Phase 5), default 0 so a pre-Phase-5 report
    # still loads; input_tokens keeps its pre-existing summed meaning.
    fresh_input_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0


class EntryReport(BaseModel):
    id: str
    status: EntryStatus
    answer: str | None = None
    verdict: str | None = None
    rationale: str | None = None
    stop_reason: str | None = None
    retrieved: list[str] | None = None
    # Phase 4's reports stored only chunk ids, not scores, which blocked any
    # offline signal study over them (plan.md §Approach Summary) -- scores
    # now ride alongside `retrieved`, same order, same length.
    retrieved_scores: list[float] | None = None
    recall_hit: bool | None = None
    usage: UsageReport | None = None
    latency_s: float | None = None
    error: str | None = None
    cited: list[str] | None = None
    fabricated: list[str] | None = None
    citation_precision: float | None = None
    coverage: float | None = None
    rewritten_query: str | None = None
    retrieval_calls: int | None = None
    capped: bool = False
    # Only AgenticPipeline populates this, and only when pruning is
    # configured -- how many accumulated chunks were dropped to keep the
    # top-N by score. None: pruning wasn't configured.
    pruned_discarded: int | None = None


class Report(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    started_at: str
    duration_s: float
    config: RunConfig
    gold_set: GoldSetRef
    corpus_hashes: dict[str, str]
    aggregates: Aggregates
    entries: list[EntryReport]


def make_run_id(name: str, started_at: datetime) -> str:
    return f"{started_at.strftime(RUN_ID_TIMESTAMP_FORMAT)}-{name}"


class ReportWriter:
    def __init__(self, runs_dir: Path):
        self.runs_dir = runs_dir

    def write(self, report: Report) -> Path:
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        path = self.runs_dir / f"{report.run_id}.json"
        path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        return path


def gold_sets_match(a: GoldSetRef, b: GoldSetRef) -> bool:
    """Path and a fingerprint of entry ids -- the identity check a Phase 0
    defect made necessary (a 29-entry rulebook run printed a delta against a
    10-entry transmission run because matching stopped at provider config).
    The single implementation `configs_match` and `evals/compare.py` both
    call, rather than each re-deriving what "the same gold set" means."""
    return a.path == b.path and a.entry_ids_fingerprint == b.entry_ids_fingerprint


def configs_match(a: RunConfig, b: RunConfig, gold_a: GoldSetRef, gold_b: GoldSetRef) -> bool:
    """Provider/pipeline config alone isn't enough -- see `gold_sets_match`."""
    return (
        a.pipeline == b.pipeline
        and a.collection == b.collection
        and a.answer.provider == b.answer.provider
        and a.answer.model == b.answer.model
        and a.judge.provider == b.judge.provider
        and a.judge.model == b.judge.model
        and a.concurrency == b.concurrency
        and gold_sets_match(gold_a, gold_b)
    )


def find_matching_prior_report(runs_dir: Path, config: RunConfig, gold_set: GoldSetRef) -> Report | None:
    """Most recent existing report with a matching config and gold-set
    identity, or None.

    Call this before writing the current run's report — once written, it
    would otherwise match itself.
    """
    if not runs_dir.exists():
        return None
    for path in sorted(runs_dir.glob("*.json"), reverse=True):
        try:
            report = Report.model_validate_json(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if configs_match(report.config, config, report.gold_set, gold_set):
            return report
    return None


DELTA_METRICS = (
    "grounded_rate",
    "refusal_correct_rate",
    "graded",
    "ungraded",
    "skipped",
    "errored",
    "recall_at_k",
    "mrr",
    "input_tokens",
    "output_tokens",
    "p50_latency_s",
    "citation_precision",
    "fabrication_rate",
    "mean_coverage",
)


def _input_tokens_per_question(report: Report) -> float | None:
    if report.gold_set.entry_count == 0:
        return None
    return report.aggregates.input_tokens / report.gold_set.entry_count


def compute_delta(previous: Report, current: Report) -> dict[str, float | None]:
    delta: dict[str, float | None] = {}
    for field_name in DELTA_METRICS:
        old_value = getattr(previous.aggregates, field_name)
        new_value = getattr(current.aggregates, field_name)
        delta[field_name] = None if old_value is None or new_value is None else new_value - old_value

    old_tpq = _input_tokens_per_question(previous)
    new_tpq = _input_tokens_per_question(current)
    delta["input_tokens_per_question"] = None if old_tpq is None or new_tpq is None else new_tpq - old_tpq
    return delta
