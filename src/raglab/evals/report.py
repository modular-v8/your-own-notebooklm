"""Run report schema, writer, and delta-vs-prior-matching-config reporting.

Retrieval-metric fields (`recall_at_k`, `mrr`, per-entry `retrieved` /
`recall_hit`) are already present here, left null. Phase 1 populates them
without a schema change — that stability is the point of building this before
the pipeline it measures.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

EntryStatus = Literal["graded", "skipped", "ungraded", "errored"]

RUN_ID_TIMESTAMP_FORMAT = "%Y-%m-%dT%H-%M-%SZ"


class RoleReportConfig(BaseModel):
    provider: str
    model: str
    params: dict[str, Any] = {}


class RunConfig(BaseModel):
    pipeline: str
    answer: RoleReportConfig
    judge: RoleReportConfig
    concurrency: int


class GoldSetRef(BaseModel):
    path: str
    version: int
    entry_count: int


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


class UsageReport(BaseModel):
    input_tokens: int
    output_tokens: int


class EntryReport(BaseModel):
    id: str
    status: EntryStatus
    answer: str | None = None
    verdict: str | None = None
    rationale: str | None = None
    stop_reason: str | None = None
    retrieved: list[str] | None = None
    recall_hit: bool | None = None
    usage: UsageReport | None = None
    latency_s: float | None = None
    error: str | None = None
    cited: list[str] | None = None
    fabricated: list[str] | None = None
    citation_precision: float | None = None
    coverage: float | None = None


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


def configs_match(a: RunConfig, b: RunConfig) -> bool:
    return (
        a.pipeline == b.pipeline
        and a.answer.provider == b.answer.provider
        and a.answer.model == b.answer.model
        and a.judge.provider == b.judge.provider
        and a.judge.model == b.judge.model
        and a.concurrency == b.concurrency
    )


def find_matching_prior_report(runs_dir: Path, config: RunConfig) -> Report | None:
    """Most recent existing report with a matching config, or None.

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
        if configs_match(report.config, config):
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
