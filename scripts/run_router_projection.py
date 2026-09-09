"""Phase 5 Milestone 4, T4.1/T4.1b: router cost projection and the tier2->tier3
signal characterization the M2 study never touched.

Zero model calls throughout -- hybrid retrieval (dense + BM25 fusion) and the
ONNX cross-encoder reranker are both local and deterministic, same as M2's
dense-only signal study.

Writes:
  evals/analysis/router_projection.md  -- T4.1: threshold sweep + cost
                                           projection at the fitted threshold
                                           and two margin-added variants
  evals/analysis/tier2_separation.md   -- T4.1b: does `spread`, recomputed
                                           after tier 2's own hybrid+rerank
                                           retrieval, separate entries tier 2
                                           resolves from ones it doesn't?

Usage: uv run python scripts/run_router_projection.py
"""

from __future__ import annotations

import json
from pathlib import Path

from raglab.analysis.oracle import TierCosts, cheapest_tier, project_router
from raglab.analysis.signal_study import (
    AUC_CHANCE_BAR,
    CHANCE_AUC,
    SignalRecord,
    auc,
    bootstrap_ci,
    clears_chance_bar,
    threshold_sweep,
)
from raglab.corpus import load_corpus
from raglab.evals.goldset import load_gold_set
from raglab.evals.report import Report
from raglab.index.embedder import Embedder
from raglab.index.store import NumpyStore
from raglab.retrieval.reranker import DEFAULT_RERANKER_MODEL, Reranker
from raglab.retrieval.retriever import Retriever
from raglab.retrieval.signals import Signals, compute_signals

ANALYSIS_DIR = Path("evals/analysis")
SIGNALS_PATH = ANALYSIS_DIR / "signals.json"
GOLD_DIR = Path("evals/gold")
CORPUS_DIR = Path("evals/corpus")
INDEX_DIR = Path("evals/index/fixed-900-150")
RUNS_DIR = Path("evals/runs")

FB_RULES = "fb_rules"
FB_RULES_GOLD = GOLD_DIR / "fb_rules.yaml"

# T3.1's fitted threshold is the observed maximum of the 13 known misses'
# spread, plus a negligible epsilon -- computed precisely below rather than
# hardcoded, since the rounded "0.051" used in prose is not exactly equal to
# either this value or the nearby sparse-sampled point M2's own sweep table
# happened to land on (see plan.md As-built notes for the reconciliation).
FITTED_THRESHOLD_EPSILON = 0.0002
MARGIN_STEP = 0.010  # two margin-added variants: +0.010 and +0.020

# Tier 2 as "hybrid + rerank" in one combined call -- hybrid-v1's fusion
# params feeding rerank-v1's cross-encoder, since Phase 4 deliberately kept
# them standalone (rerank-v1's own comment: "isolates reranking's own effect
# from hybrid's") and no combined config has ever been run.
TIER2_MODE = "hybrid"
TIER2_CANDIDATE_K = 20
TIER2_RRF_K = 60
TIER2_K = 5


def _mean_tokens_per_entry(report_path: Path) -> float:
    report = Report.model_validate_json(report_path.read_text(encoding="utf-8"))
    return report.aggregates.input_tokens / report.gold_set.entry_count


def _find_report(pattern: str) -> Path:
    matches = sorted(RUNS_DIR.glob(pattern))
    if not matches:
        raise SystemExit(f"no report matches {pattern!r} in {RUNS_DIR}")
    return matches[-1]


def _load_tier_costs() -> TierCosts:
    tier1 = _mean_tokens_per_entry(_find_report("*phase4_fb_rules_baseline*.json"))
    hybrid = _mean_tokens_per_entry(_find_report("*phase4_hybrid_v1_fb_rules*.json"))
    rerank = _mean_tokens_per_entry(_find_report("*phase4_rerank_v1_fb_rules*.json"))
    tier3 = _mean_tokens_per_entry(_find_report("*phase4_agentic_v1_fb_rules_full*.json"))
    return TierCosts(tier1=tier1, tier2=(hybrid + rerank) / 2, tier3=tier3)


def _load_fb_records() -> list[SignalRecord]:
    rows = json.loads(SIGNALS_PATH.read_text(encoding="utf-8"))
    records = []
    for row in rows:
        if row["gold_set"] != FB_RULES or row["recall_hit"].get("baseline") is None:
            continue
        records.append(
            SignalRecord(
                gold_set=row["gold_set"],
                entry_id=row["entry_id"],
                tags=tuple(row["tags"]),
                is_follow_up=row["is_follow_up"],
                signals=Signals(**row["signals"]),
                recall_hit=row["recall_hit"],
            )
        )
    return records


def _fitted_threshold(records: list[SignalRecord]) -> float:
    """The observed maximum spread among known misses, plus a negligible
    epsilon -- zero headroom, fitted to this exact sample (plan.md Tech
    Stack: "Threshold margin")."""
    miss_spreads = [r.signals.spread for r in records if r.recall_hit["baseline"] is False]
    return max(miss_spreads) + FITTED_THRESHOLD_EPSILON


def _write_router_projection(records: list[SignalRecord], costs: TierCosts, fitted_threshold: float) -> None:
    labels = [bool(r.recall_hit["baseline"]) for r in records]
    spread_scores = [r.signals.spread for r in records]
    n_misses = sum(1 for label in labels if not label)
    n_hits = len(labels) - n_misses

    # Which tier fixes each miss is fixed data (Phase 4's own outcomes) and
    # doesn't change with the threshold -- only how many *hits* get dragged
    # along as false escalations does.
    miss_tiers = [cheapest_tier(r) for r in records if not r.recall_hit["baseline"]]
    fixed_by_tier2 = sum(1 for t in miss_tiers if t == "tier2")
    fixed_by_tier3 = sum(1 for t in miss_tiers if t == "tier3")
    unfixed = sum(1 for t in miss_tiers if t == "unfixed")

    lines = [
        "# Router cost projection (Phase 5, T4.1)",
        "",
        f"`fb_rules`, 53 baseline-scored entries ({n_misses} misses, {n_hits} hits). Escalation rule: "
        "escalate to tier 2 when `spread <= threshold`. Two cost columns, because T4.1b (below) found no "
        "cheap signal to decide tier2->tier3: **with-filter** assumes a tier2->tier3 stopping signal "
        "exists (an upper bound, not yet buildable); **no-filter** is the realistic number -- every "
        "tier-2-reached entry proceeds to tier 3 unconditionally. Recall is identical in both columns "
        "(additive escalation means an unneeded tier 3 pass can't lose a chunk already held).",
        "",
        f"Of the {n_misses} misses (constant across every threshold below, since all three catch every "
        f"miss): {fixed_by_tier2} resolved at tier 2, {fixed_by_tier3} need tier 3, {unfixed} unfixed by "
        "anything Phase 4 ever ran (still pays the full ladder and still misses, under either column).",
        "",
        "Reference points: baseline alone costs 170,513 for 75.5% recall; always-agentic costs 618,459 "
        "for 98.1% recall; the oracle (perfect foresight, stops early on `q-018`) costs 255,427 for the "
        "same 98.1% (`evals/analysis/oracle.md`).",
        "",
        f"The fitted threshold ({fitted_threshold:.6f}) is computed precisely here as max(miss spread) + "
        f"{FITTED_THRESHOLD_EPSILON} -- `evals/analysis/separation.md`'s own sweep table displays its "
        "closest row as \"0.051\" too, but that row's exact value (0.05090749..., one hit's own spread, "
        "picked up by chance from an evenly-spaced sparse sample of observed scores) is a different "
        "number that happens to round the same way. Both separate the same 13 misses from the same "
        "40 hits except for one boundary entry (`q-013`); the difference is immaterial to the verdict "
        "but stated here rather than silently reconciled.",
        "",
        "| threshold | escalation rate | misses caught | hits wrongly escalated | projected recall | "
        "cost (with-filter) | cost (no-filter) | saving vs agentic (no-filter) |",
        "|---|---|---|---|---|---|---|---|",
    ]

    always_agentic_cost = costs.tier3 * len(records)
    thresholds = [fitted_threshold, fitted_threshold + MARGIN_STEP, fitted_threshold + 2 * MARGIN_STEP]
    no_filter_projections = {}
    for threshold in thresholds:
        sweep = threshold_sweep(labels, spread_scores, [threshold])[0]
        with_filter = project_router(records, threshold, costs, tier2_filter=True)
        no_filter = project_router(records, threshold, costs, tier2_filter=False)
        no_filter_projections[threshold] = no_filter
        margin_note = "fitted" if threshold == fitted_threshold else f"+{threshold - fitted_threshold:.3f} margin"
        saving = 1 - no_filter.projected_cost / always_agentic_cost
        lines.append(
            f"| {threshold:.4f} ({margin_note}) | {sweep.escalation_rate:.1%} | "
            f"{sweep.misses_caught}/{n_misses} | {sweep.hits_wrongly_escalated}/{n_hits} | "
            f"{with_filter.projected_recall:.1%} | {with_filter.projected_cost:,.0f} | "
            f"{no_filter.projected_cost:,.0f} | {saving:.1%} |"
        )

    lines.append("")
    fitted_no_filter = no_filter_projections[fitted_threshold]
    fitted_saving = 1 - fitted_no_filter.projected_cost / always_agentic_cost
    lines.append(
        f"**Realistic number (no tier2->tier3 filter, per T4.1b): at the fitted threshold, projected "
        f"cost is {fitted_no_filter.projected_cost:,.0f}** against always-agentic's {always_agentic_cost:,.0f} "
        f"-- a projected saving of {fitted_saving:.1%}, for the identical {fitted_no_filter.projected_recall:.1%} "
        "recall ceiling (the router cannot beat agentic's recall, only its cost, per plan.md's Milestone 4 "
        "framing). This is the number T4.2's go/no-go decision uses."
    )

    path = ANALYSIS_DIR / "router_projection.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {path}")


# count_above is excluded here: its absolute threshold (0.35) is meaningful
# only on cosine similarity, not the reranker's cross-encoder score scale.
# top1/margin/spread/doc_agreement are all scale-independent (differences,
# maxima, or counts), so they carry over without modification.
TIER2_SIGNAL_NAMES = ("top1", "margin", "spread", "doc_agreement")


def _write_tier2_separation(
    records: list[SignalRecord], gold, retriever: Retriever, reranker: Reranker, fitted_threshold: float
) -> None:
    escalated = [r for r in records if r.signals.spread <= fitted_threshold]
    entries_by_id = {e.id: e for e in gold.entries}

    signal_scores: dict[str, list[float]] = {name: [] for name in TIER2_SIGNAL_NAMES}
    labels = []
    for record in escalated:
        entry = entries_by_id[record.entry_id]
        chunks = retriever.search(
            entry.question,
            k=TIER2_K,
            collection=gold.collection,
            mode=TIER2_MODE,
            candidate_k=TIER2_CANDIDATE_K,
            rrf_k=TIER2_RRF_K,
            reranker=reranker,
        )
        signals = compute_signals(chunks, threshold=float("-inf"))  # count_above unused here
        for name in TIER2_SIGNAL_NAMES:
            signal_scores[name].append(getattr(signals, name))
        labels.append(cheapest_tier(record) in ("tier1", "tier2"))

    n = len(escalated)
    n_resolved = sum(labels)
    n_unresolved = n - n_resolved

    lines = [
        "# Tier 2 -> tier 3 signal characterization (Phase 5, T4.1b)",
        "",
        f"The {n} entries `fb_rules` escalates at the tier1 threshold (spread <= {fitted_threshold:.6f}), "
        f"re-retrieved with tier 2's own combined hybrid+rerank config (mode={TIER2_MODE}, "
        f"candidate_k={TIER2_CANDIDATE_K}, rrf_k={TIER2_RRF_K}, reranker={DEFAULT_RERANKER_MODEL}) -- a real "
        "retrieval, not a reuse of tier 1's scores, since this scale is the cross-encoder's, not cosine "
        "similarity. Label: resolved after tier 1 + tier 2 additively (baseline hit, or hybrid-v1/"
        f"rerank-v1 hit) -- {n_resolved} resolved, {n_unresolved} still need tier 3 or are unfixed by "
        f"anything Phase 4 ran. All four scale-independent candidate signals tested, not just `spread` "
        "-- `count_above` is excluded, its absolute threshold has no meaning on the reranker's score scale.",
        "",
        "| signal | AUC | 95% CI | clears bar? |",
        "|---|---|---|---|",
    ]

    winners = []
    for name in TIER2_SIGNAL_NAMES:
        scores = signal_scores[name]
        try:
            auc_value = auc(labels, scores)
        except ValueError:
            lines.append(f"| `{name}` | n/a | n/a | no (degenerate) |")
            continue
        ci = bootstrap_ci(labels, scores, seed=0)
        clears = clears_chance_bar(auc_value, ci)
        if clears:
            winners.append((name, auc_value, ci))
        lines.append(f"| `{name}` | {auc_value:.3f} | [{ci[0]:.3f}, {ci[1]:.3f}] | {'YES' if clears else 'no'} |")

    lines.append("")
    lines.append(f"Chance bar: AUC >= {AUC_CHANCE_BAR} and CI excludes {CHANCE_AUC}. n={n} ({n_unresolved} negative).")
    lines.append("")

    if winners:
        winners.sort(key=lambda w: w[1], reverse=True)
        best_name, best_auc, best_ci = winners[0]
        lines.append(
            f"**Verdict: `{best_name}` clears the bar** (AUC={best_auc:.3f}, 95% CI=[{best_ci[0]:.3f}, "
            f"{best_ci[1]:.3f}]) -- tier2->tier3 escalation can use a recalibrated threshold on this "
            "combined retrieval's own scale."
        )
    else:
        lines.append(
            "**Verdict: none of the four candidate signals clears the bar on this population.** Tier 3 "
            "must be entered unconditionally for every tier-2-reached entry that reaches this point -- "
            "there is no cheap way, with any of these signals at this sample size, to tell a "
            "tier-2-resolved entry from one that still needs tier 3. This raises the router's realistic "
            "projected cost well above what an oracle-informed stop-at-tier-2 would suggest -- see "
            "`router_projection.md`'s revised, no-filter cost line."
        )

    path = ANALYSIS_DIR / "tier2_separation.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {path}")


def main() -> None:
    records = _load_fb_records()
    costs = _load_tier_costs()
    fitted_threshold = _fitted_threshold(records)
    _write_router_projection(records, costs, fitted_threshold)

    documents = load_corpus(CORPUS_DIR)
    gold = load_gold_set(FB_RULES_GOLD)
    for name, expected_hash in gold.corpus_hashes.items():
        doc = documents.get(name)
        if doc is None or doc.sha256 != expected_hash:
            raise SystemExit(f"{FB_RULES_GOLD}: corpus hash mismatch for {name!r}")

    store = NumpyStore(INDEX_DIR)
    retriever = Retriever(store, Embedder())
    reranker = Reranker()
    _write_tier2_separation(records, gold, retriever, reranker, fitted_threshold)


if __name__ == "__main__":
    main()
