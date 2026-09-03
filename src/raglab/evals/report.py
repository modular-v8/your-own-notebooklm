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
    "input_tokens",
    "output_tokens",
    "p50_latency_s",
)


def compute_delta(previous: Report, current: Report) -> dict[str, float | None]:
    delta: dict[str, float | None] = {}
    for field_name in DELTA_METRICS:
        old_value = getattr(previous.aggregates, field_name)
        new_value = getattr(current.aggregates, field_name)
        delta[field_name] = None if old_value is None or new_value is None else new_value - old_value
    return delta
