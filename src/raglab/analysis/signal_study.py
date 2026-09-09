"""Offline signal study (Phase 5, T2.2/T2.3): recompute every candidate
signal for every gold entry from the on-disk index, join Phase 4's recorded
recall_hit outcomes, and measure how well each signal separates the
baseline's recall misses from its hits. Retrieval is deterministic and
entirely local (plan.md, Approach Summary), so every step here runs with
zero model calls.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from ..evals.goldset import GoldSet
from ..evals.report import Report
from ..retrieval.retriever import Retriever
from ..retrieval.signals import Signals, compute_signals

DEFAULT_TOP_K = 5
DEFAULT_SCORE_THRESHOLD = 0.35

# Named ExperimentConfigs a report must carry to count here -- a report with
# no experiment recorded predates Phase 4's frozen configs and isn't one of
# the ladder's rungs, so it's excluded rather than guessed at.
EXPERIMENT_NAMES = ("baseline", "hybrid-v1", "rerank-v1", "agentic-v1")

SIGNAL_NAMES = ("top1", "margin", "spread", "count_above", "doc_agreement")

# "Better than chance" bar (plan.md, Tech Stack): a single number without an
# interval at this sample size would license building a router on noise.
AUC_CHANCE_BAR = 0.65
CHANCE_AUC = 0.50


@dataclass(frozen=True)
class SignalRecord:
    gold_set: str
    entry_id: str
    tags: tuple[str, ...]
    is_follow_up: bool
    signals: Signals
    # Keyed by EXPERIMENT_NAMES; None where that experiment was never run
    # against this entry (only fb_rules has hybrid-v1/rerank-v1/agentic-v1;
    # every gold set but scoping has baseline) or the entry has no gold span
    # to score recall against (e.g. not-in-document).
    recall_hit: dict[str, bool | None]


def signal_value(record: SignalRecord, name: str) -> float:
    return float(getattr(record.signals, name))


def record_to_dict(record: SignalRecord) -> dict:
    return {
        "gold_set": record.gold_set,
        "entry_id": record.entry_id,
        "tags": list(record.tags),
        "is_follow_up": record.is_follow_up,
        "signals": asdict(record.signals),
        "recall_hit": record.recall_hit,
    }


def load_recall_hits(runs_dir: Path) -> dict[str, dict[str, dict[str, bool | None]]]:
    """{experiment_name: {gold_set_stem: {entry_id: recall_hit}}}.

    Reports sort chronologically by their timestamp-prefixed filename, so
    keeping the last one seen per (experiment, gold set) picks Phase 4's
    frozen full run over an earlier subset probe (e.g. agentic-v1's
    fb_rules full run over its own earlier 20-entry subset) without either
    being named explicitly.
    """
    result: dict[str, dict[str, dict[str, bool | None]]] = {name: {} for name in EXPERIMENT_NAMES}
    seen_run_id: dict[tuple[str, str], str] = {}

    for path in sorted(runs_dir.glob("*.json")):
        try:
            report = Report.model_validate_json(path.read_text(encoding="utf-8"))
        except ValueError:
            continue

        experiment = report.config.experiment
        if experiment is None or experiment.name not in EXPERIMENT_NAMES:
            continue

        gold_stem = Path(report.gold_set.path).stem
        key = (experiment.name, gold_stem)
        if seen_run_id.get(key, "") > report.run_id:
            continue
        seen_run_id[key] = report.run_id

        result[experiment.name][gold_stem] = {entry.id: entry.recall_hit for entry in report.entries}

    return result


def build_signal_records(
    gold_sets: dict[str, GoldSet],
    retriever: Retriever,
    recall_hits: dict[str, dict[str, dict[str, bool | None]]],
    *,
    top_k: int = DEFAULT_TOP_K,
    threshold: float = DEFAULT_SCORE_THRESHOLD,
) -> list[SignalRecord]:
    records = []
    for gold_stem, gold in gold_sets.items():
        for entry in gold.entries:
            chunks = retriever.search(entry.question, k=top_k, collection=gold.collection, mode="dense")
            signals = compute_signals(chunks, threshold)
            recall_hit = {
                name: recall_hits.get(name, {}).get(gold_stem, {}).get(entry.id) for name in EXPERIMENT_NAMES
            }
            records.append(
                SignalRecord(
                    gold_set=gold_stem,
                    entry_id=entry.id,
                    tags=tuple(entry.tags),
                    is_follow_up=entry.is_follow_up,
                    signals=signals,
                    recall_hit=recall_hit,
                )
            )
    return records


def baseline_scored_records(records: list[SignalRecord], gold_set: str) -> list[SignalRecord]:
    """Entries from one gold set with a baseline recall_hit to learn from --
    excludes not-in-document entries (no gold span, recall_hit is None)."""
    return [r for r in records if r.gold_set == gold_set and r.recall_hit.get("baseline") is not None]


def auc(labels: list[bool], scores: list[float]) -> float:
    """P(a random positive scores higher than a random negative) via the
    Mann-Whitney U statistic, with tied scores broken by average rank."""
    n_pos = sum(labels)
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        raise ValueError("auc requires at least one positive and one negative label")

    order = sorted(range(len(scores)), key=lambda i: scores[i])
    ranks = [0.0] * len(scores)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        avg_rank = (i + j) / 2 + 1  # 1-based average rank across the tied block
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1

    rank_sum_pos = sum(rank for rank, label in zip(ranks, labels) if label)
    return (rank_sum_pos - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def bootstrap_ci(
    labels: list[bool],
    scores: list[float],
    *,
    n_boot: int = 2000,
    confidence: float = 0.95,
    seed: int = 0,
) -> tuple[float, float]:
    """Non-parametric bootstrap CI on the AUC -- resamples that lose either
    class entirely are skipped (AUC is undefined there), not counted."""
    rng = np.random.default_rng(seed)
    n = len(labels)
    labels_arr = np.asarray(labels)
    scores_arr = np.asarray(scores, dtype=float)

    estimates = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        sample_labels = labels_arr[idx]
        if sample_labels.all() or not sample_labels.any():
            continue
        estimates.append(auc(list(sample_labels), list(scores_arr[idx])))

    if not estimates:
        raise ValueError("bootstrap produced no resamples with both classes present")

    lower_q = (1 - confidence) / 2
    return float(np.quantile(estimates, lower_q)), float(np.quantile(estimates, 1 - lower_q))


def clears_chance_bar(auc_value: float, ci: tuple[float, float]) -> bool:
    lo, hi = ci
    return auc_value >= AUC_CHANCE_BAR and not (lo <= CHANCE_AUC <= hi)


@dataclass(frozen=True)
class ThresholdPoint:
    threshold: float
    escalation_rate: float
    misses_caught: int
    hits_wrongly_escalated: int


def candidate_thresholds(scores: list[float]) -> list[float]:
    return sorted(set(scores))


def threshold_sweep(labels: list[bool], scores: list[float], thresholds: list[float]) -> list[ThresholdPoint]:
    """At each threshold, escalate (distrust tier 1) whenever a score is at
    or below it -- a low value means "weak match" (plan.md: "spread >
    threshold? -> stop", i.e. escalate iff spread <= threshold)."""
    points = []
    for threshold in thresholds:
        escalated = [score <= threshold for score in scores]
        escalation_rate = sum(escalated) / len(labels) if labels else 0.0
        misses_caught = sum(1 for label, esc in zip(labels, escalated) if not label and esc)
        hits_wrongly_escalated = sum(1 for label, esc in zip(labels, escalated) if label and esc)
        points.append(ThresholdPoint(threshold, escalation_rate, misses_caught, hits_wrongly_escalated))
    return points
