"""Paired per-entry comparison between two run reports (specs/4-retrieval-
optimization/plan.md, Milestone 2). Every technique this phase tests is
judged against the frozen baseline entry by entry, never on an aggregate
delta alone (spec prior decision: "a technique is kept if it fixes at least
two entries and breaks none").

Only `recall_hit`, `coverage`, and `citation_precision` classify an entry --
all three are span-based and defined identically regardless of chunk size
or count (Phase 1's any-overlap rule), which is what keeps them comparable
even across the structure-aware chunking experiment. `grounded_rate` is
reported per entry but never classifies, per the same judge-noise finding
that made it secondary throughout Phase 4 (see plan.md's As-built notes).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .report import EntryReport, Report, gold_sets_match

Classification = Literal["win", "loss", "tie"]
MetricClassification = Literal["win", "loss", "tie", "n/a"]


class CompareError(Exception):
    pass


@dataclass(frozen=True)
class MetricDelta:
    baseline: bool | float | None
    experiment: bool | float | None
    classification: MetricClassification


@dataclass(frozen=True)
class EntryComparison:
    id: str
    classification: Classification
    metrics: dict[str, MetricDelta]
    baseline_verdict: str | None
    experiment_verdict: str | None

    @property
    def regressed_metrics(self) -> list[str]:
        return [name for name, delta in self.metrics.items() if delta.classification == "loss"]


@dataclass(frozen=True)
class TagCompareCounts:
    count: int
    wins: int
    losses: int
    ties: int


@dataclass(frozen=True)
class CompareResult:
    wins: int
    losses: int
    ties: int
    excluded: list[str]  # entry ids excluded: errored in either run
    entries: list[EntryComparison]
    by_tag: dict[str, TagCompareCounts]
    chunking_mismatch: bool
    chunking_note: str | None

    @property
    def regressed(self) -> list[EntryComparison]:
        return [e for e in self.entries if e.classification == "loss"]


def _classify_bool(baseline: bool | None, experiment: bool | None) -> MetricClassification:
    if baseline is None or experiment is None:
        return "n/a"
    if baseline == experiment:
        return "tie"
    return "win" if experiment else "loss"


def _classify_float(baseline: float | None, experiment: float | None) -> MetricClassification:
    if baseline is None or experiment is None:
        return "n/a"
    if experiment > baseline:
        return "win"
    if experiment < baseline:
        return "loss"
    return "tie"


def _entry_rollup(metrics: dict[str, MetricDelta]) -> Classification:
    classes = {delta.classification for delta in metrics.values()}
    if "loss" in classes:
        return "loss"
    if "win" in classes:
        return "win"
    return "tie"


def _compare_entry(baseline_entry: EntryReport, experiment_entry: EntryReport) -> EntryComparison:
    metrics = {
        "recall_hit": MetricDelta(
            baseline_entry.recall_hit,
            experiment_entry.recall_hit,
            _classify_bool(baseline_entry.recall_hit, experiment_entry.recall_hit),
        ),
        "coverage": MetricDelta(
            baseline_entry.coverage,
            experiment_entry.coverage,
            _classify_float(baseline_entry.coverage, experiment_entry.coverage),
        ),
        "citation_precision": MetricDelta(
            baseline_entry.citation_precision,
            experiment_entry.citation_precision,
            _classify_float(baseline_entry.citation_precision, experiment_entry.citation_precision),
        ),
    }
    return EntryComparison(
        id=baseline_entry.id,
        classification=_entry_rollup(metrics),
        metrics=metrics,
        baseline_verdict=baseline_entry.verdict,
        experiment_verdict=experiment_entry.verdict,
    )


def _compute_by_tag(
    entries: list[EntryComparison], tags_by_id: dict[str, list[str]]
) -> dict[str, TagCompareCounts]:
    grouped: dict[str, list[EntryComparison]] = {}
    for entry in entries:
        for tag in tags_by_id.get(entry.id, []):
            grouped.setdefault(tag, []).append(entry)
    return {
        tag: TagCompareCounts(
            count=len(es),
            wins=sum(1 for e in es if e.classification == "win"),
            losses=sum(1 for e in es if e.classification == "loss"),
            ties=sum(1 for e in es if e.classification == "tie"),
        )
        for tag, es in sorted(grouped.items())
    }


def compare_reports(
    baseline: Report, experiment: Report, tags_by_id: dict[str, list[str]] | None = None
) -> CompareResult:
    if baseline.config.experiment is None:
        raise CompareError(
            f"{baseline.run_id}: no recorded experiment config; cannot use as a paired comparison source"
        )
    if experiment.config.experiment is None:
        raise CompareError(
            f"{experiment.run_id}: no recorded experiment config; cannot use as a paired comparison source"
        )
    if not gold_sets_match(baseline.gold_set, experiment.gold_set):
        raise CompareError(
            f"gold-set mismatch: {baseline.run_id} ({baseline.gold_set.path}) uses a different "
            f"gold set than {experiment.run_id} ({experiment.gold_set.path}); refusing to compare "
            "across different question sets"
        )

    baseline_chunking = baseline.config.experiment.chunking
    experiment_chunking = experiment.config.experiment.chunking
    chunking_mismatch = baseline_chunking != experiment_chunking
    chunking_note = (
        f"Note: chunking differs ({baseline_chunking} vs {experiment_chunking}) -- "
        "retrieved id lists are not comparable across this change; only span-based "
        "metrics (recall_hit, coverage, citation_precision) are reported."
        if chunking_mismatch
        else None
    )

    baseline_by_id = {e.id: e for e in baseline.entries}
    experiment_by_id = {e.id: e for e in experiment.entries}

    entries: list[EntryComparison] = []
    excluded: list[str] = []
    for entry_id, baseline_entry in baseline_by_id.items():
        experiment_entry = experiment_by_id.get(entry_id)
        if experiment_entry is None:
            continue
        if baseline_entry.status == "errored" or experiment_entry.status == "errored":
            excluded.append(entry_id)
            continue
        entries.append(_compare_entry(baseline_entry, experiment_entry))

    return CompareResult(
        wins=sum(1 for e in entries if e.classification == "win"),
        losses=sum(1 for e in entries if e.classification == "loss"),
        ties=sum(1 for e in entries if e.classification == "tie"),
        excluded=excluded,
        entries=entries,
        by_tag=_compute_by_tag(entries, tags_by_id or {}),
        chunking_mismatch=chunking_mismatch,
        chunking_note=chunking_note,
    )
