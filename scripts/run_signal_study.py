"""Phase 5 Milestone 2: offline signal study + oracle ladder.

Zero model calls -- retrieval is deterministic and entirely local (spec.md
plan.md, Approach Summary). Recomputes every candidate signal for all 99
gold entries from the on-disk `fixed-900-150` index, joins Phase 4's
recorded recall_hit outcomes, and writes:

  evals/analysis/signals.json    -- per-entry signals + recall_hit, all 99
  evals/analysis/separation.md   -- AUC/CI/sweep per signal, fb_rules only
  evals/analysis/oracle.md       -- perfect-routing ceiling, fb_rules only

The separation and oracle analyses are scoped to fb_rules specifically: it's
the only gold set with hybrid-v1/rerank-v1/agentic-v1 recall_hit recorded
(needed for the oracle), and the one named in spec.md's "14 misses / 43
hits" framing (T2.3/T2.5). signals.json itself covers all 99 for
completeness and any later reuse.

Usage: uv run python scripts/run_signal_study.py
"""

from __future__ import annotations

import json
from pathlib import Path

from raglab.analysis.oracle import TierCosts, compute_oracle
from raglab.analysis.signal_study import (
    AUC_CHANCE_BAR,
    CHANCE_AUC,
    SIGNAL_NAMES,
    auc,
    baseline_scored_records,
    bootstrap_ci,
    build_signal_records,
    candidate_thresholds,
    clears_chance_bar,
    load_recall_hits,
    record_to_dict,
    signal_value,
    threshold_sweep,
)
from raglab.corpus import load_corpus
from raglab.evals.goldset import GoldSet, load_gold_set
from raglab.evals.report import Report
from raglab.index.embedder import Embedder
from raglab.index.store import NumpyStore
from raglab.retrieval.retriever import Retriever

GOLD_DIR = Path("evals/gold")
CORPUS_DIR = Path("evals/corpus")
INDEX_DIR = Path("evals/index/fixed-900-150")
RUNS_DIR = Path("evals/runs")
ANALYSIS_DIR = Path("evals/analysis")

FB_RULES = "fb_rules"

SWEEP_THRESHOLD_COUNT = 10


def _load_gold_sets() -> dict[str, GoldSet]:
    documents = load_corpus(CORPUS_DIR)
    gold_sets: dict[str, GoldSet] = {}
    for path in sorted(GOLD_DIR.glob("*.yaml")):
        gold = load_gold_set(path)
        for name, expected_hash in gold.corpus_hashes.items():
            doc = documents.get(name)
            if doc is None or doc.sha256 != expected_hash:
                raise SystemExit(f"{path}: corpus hash mismatch for {name!r} -- rebuild the index first")
        gold_sets[path.stem] = gold
    return gold_sets


def _mean_tokens_per_entry(report_path: Path) -> float:
    report = Report.model_validate_json(report_path.read_text(encoding="utf-8"))
    return report.aggregates.input_tokens / report.gold_set.entry_count


def _find_report(pattern: str) -> Path:
    matches = sorted(RUNS_DIR.glob(pattern))
    if not matches:
        raise SystemExit(f"no report matches {pattern!r} in {RUNS_DIR}")
    return matches[-1]  # lexical sort on timestamp-prefixed filenames == chronological


def _sparse_sweep_thresholds(scores: list[float]) -> list[float]:
    """Every distinct score is a valid cut point, but printing all of them
    for a signal like `top1` is unreadable -- take an evenly spaced subset."""
    all_thresholds = candidate_thresholds(scores)
    if len(all_thresholds) <= SWEEP_THRESHOLD_COUNT:
        return all_thresholds
    step = (len(all_thresholds) - 1) / (SWEEP_THRESHOLD_COUNT - 1)
    return [all_thresholds[round(i * step)] for i in range(SWEEP_THRESHOLD_COUNT)]


def main() -> None:
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)

    gold_sets = _load_gold_sets()
    store = NumpyStore(INDEX_DIR)
    retriever = Retriever(store, Embedder())
    recall_hits = load_recall_hits(RUNS_DIR)

    records = build_signal_records(gold_sets, retriever, recall_hits)
    signals_path = ANALYSIS_DIR / "signals.json"
    signals_path.write_text(
        json.dumps([record_to_dict(r) for r in records], indent=2), encoding="utf-8"
    )
    print(f"Wrote {signals_path} ({len(records)} entries)")

    fb_records = baseline_scored_records(records, FB_RULES)
    labels = [bool(r.recall_hit["baseline"]) for r in fb_records]
    n_hits = sum(labels)
    n_misses = len(labels) - n_hits
    print(f"{FB_RULES}: {len(fb_records)} baseline-scored entries ({n_misses} misses, {n_hits} hits)")

    separation_lines = [
        "# Signal separation study (Phase 5, T2.3/T2.5)",
        "",
        f"Baseline recall on `{FB_RULES}`: {n_hits} hits, {n_misses} misses, {len(fb_records)} scored"
        " (not-in-document entries excluded -- no gold span to score recall against).",
        "",
        f"Chance bar: AUC >= {AUC_CHANCE_BAR} and the bootstrap 95% CI excludes {CHANCE_AUC}.",
        "",
        "| signal | AUC | 95% CI | clears bar? |",
        "|---|---|---|---|",
    ]

    winners: list[tuple[str, float, tuple[float, float]]] = []
    per_signal_scores: dict[str, list[float]] = {}

    for name in SIGNAL_NAMES:
        scores = [signal_value(r, name) for r in fb_records]
        per_signal_scores[name] = scores
        try:
            auc_value = auc(labels, scores)
        except ValueError:
            separation_lines.append(f"| `{name}` | n/a | n/a | no (degenerate: one class empty) |")
            continue
        ci = bootstrap_ci(labels, scores, seed=0)
        clears = clears_chance_bar(auc_value, ci)
        if clears:
            winners.append((name, auc_value, ci))
        separation_lines.append(
            f"| `{name}` | {auc_value:.3f} | [{ci[0]:.3f}, {ci[1]:.3f}] | {'YES' if clears else 'no'} |"
        )

    separation_lines.append("")
    if winners:
        winners.sort(key=lambda w: w[1], reverse=True)
        best_name, best_auc, best_ci = winners[0]
        separation_lines.append(
            f"**Verdict: `{best_name}` clears the chance bar** (AUC={best_auc:.3f}, "
            f"95% CI=[{best_ci[0]:.3f}, {best_ci[1]:.3f}]) -- a proxy router is viable on this corpus."
        )
    else:
        separation_lines.append(
            "**Verdict: no candidate signal clears the chance bar** -- none separates the baseline's "
            f"{n_misses} misses from its {n_hits} hits better than chance on this corpus. "
            "Per spec's unwanted-behavior clause, no proxy router is built on any of these signals; "
            "the gate falls through to the self-assessment probe (T3.2)."
        )

    separation_lines.append("")
    separation_lines.append("## Threshold sweep")
    separation_lines.append("")
    for name in SIGNAL_NAMES:
        scores = per_signal_scores[name]
        thresholds = _sparse_sweep_thresholds(scores)
        if not thresholds:
            continue
        separation_lines.append(f"### `{name}`")
        separation_lines.append("")
        separation_lines.append("| threshold | escalation rate | misses caught | hits wrongly escalated |")
        separation_lines.append("|---|---|---|---|")
        for point in threshold_sweep(labels, scores, thresholds):
            separation_lines.append(
                f"| {point.threshold:.3f} | {point.escalation_rate:.1%} | "
                f"{point.misses_caught}/{n_misses} | {point.hits_wrongly_escalated}/{n_hits} |"
            )
        separation_lines.append("")

    separation_path = ANALYSIS_DIR / "separation.md"
    separation_path.write_text("\n".join(separation_lines) + "\n", encoding="utf-8")
    print(f"Wrote {separation_path}")

    tier1_cost = _mean_tokens_per_entry(_find_report("*phase4_fb_rules_baseline*.json"))
    hybrid_cost = _mean_tokens_per_entry(_find_report("*phase4_hybrid_v1_fb_rules*.json"))
    rerank_cost = _mean_tokens_per_entry(_find_report("*phase4_rerank_v1_fb_rules*.json"))
    agentic_cost = _mean_tokens_per_entry(_find_report("*phase4_agentic_v1_fb_rules_full*.json"))
    costs = TierCosts(tier1=tier1_cost, tier2=(hybrid_cost + rerank_cost) / 2, tier3=agentic_cost)

    oracle = compute_oracle(fb_records, costs)
    agentic_hits = sum(1 for r in fb_records if r.recall_hit.get("agentic-v1"))
    agentic_recall = agentic_hits / oracle.total_scored

    oracle_lines = [
        "# Oracle upper bound (Phase 5, T2.4)",
        "",
        "For each of the baseline's recall misses, the cheapest Phase 4 tier that already fixed it "
        "-- an upper bound, not a real router, computed entirely from recorded Phase 4 outcomes. "
        "Tier 2 (`hybrid-v1` + `rerank-v1`) counts an entry as fixed if either standalone config found "
        "it, since no combined tier-2 config has been run.",
        "",
        "Per-entry mean input tokens, from Phase 4's own reports:",
        f"- tier 1 (baseline): {tier1_cost:,.0f}",
        f"- tier 2 (avg of hybrid-v1 {hybrid_cost:,.0f} and rerank-v1 {rerank_cost:,.0f}): {costs.tier2:,.0f}",
        f"- tier 3 (agentic-v1): {agentic_cost:,.0f}",
        "",
        f"| | recall ({oracle.total_scored} entries) | cost |",
        "|---|---|---|",
        f"| baseline alone | {oracle.baseline_hits}/{oracle.total_scored} = {oracle.baseline_hits / oracle.total_scored:.1%} | {oracle.baseline_cost:,.0f} |",
        f"| always-agentic | {agentic_hits}/{oracle.total_scored} = {agentic_recall:.1%} | {oracle.always_agentic_cost:,.0f} |",
        f"| **oracle** | {oracle.baseline_hits + oracle.fixed_by_tier2 + oracle.fixed_by_tier3}/{oracle.total_scored} = {oracle.oracle_recall:.1%} | {oracle.oracle_cost:,.0f} |",
        "",
        f"Miss breakdown: {oracle.baseline_hits} already hit by baseline, {oracle.fixed_by_tier2} fixed by "
        f"tier 2, {oracle.fixed_by_tier3} fixed only by tier 3, {oracle.unfixed} unfixed by anything Phase 4 ran.",
        "",
        f"Oracle recall ({oracle.oracle_recall:.1%}) against always-agentic's own measured recall on this "
        f"subset ({agentic_recall:.1%}), at {oracle.oracle_cost / oracle.always_agentic_cost:.1%} of "
        "always-agentic's cost.",
    ]

    oracle_path = ANALYSIS_DIR / "oracle.md"
    oracle_path.write_text("\n".join(oracle_lines) + "\n", encoding="utf-8")
    print(f"Wrote {oracle_path}")


if __name__ == "__main__":
    main()
