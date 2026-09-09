"""Cheapest-tier selection and oracle cost/recall accounting (Phase 5, T2.4)."""

from __future__ import annotations

from raglab.analysis.oracle import TierCosts, cheapest_tier, compute_oracle, project_router
from raglab.analysis.signal_study import SignalRecord
from raglab.retrieval.signals import Signals

_ZERO_SIGNALS = Signals(top1=0.0, margin=0.0, spread=0.0, count_above=0, doc_agreement=0)


def _record(entry_id: str, recall_hit: dict, spread: float = 0.0) -> SignalRecord:
    full = {"baseline": None, "hybrid-v1": None, "rerank-v1": None, "agentic-v1": None}
    full.update(recall_hit)
    signals = Signals(top1=0.0, margin=0.0, spread=spread, count_above=0, doc_agreement=0)
    return SignalRecord(
        gold_set="fb_rules", entry_id=entry_id, tags=(), is_follow_up=False, signals=signals, recall_hit=full
    )


def test_cheapest_tier_baseline_hit_needs_no_escalation():
    record = _record("q-1", {"baseline": True})
    assert cheapest_tier(record) == "tier1"


def test_cheapest_tier_fixed_by_hybrid_only():
    record = _record("q-2", {"baseline": False, "hybrid-v1": True, "rerank-v1": False, "agentic-v1": True})
    assert cheapest_tier(record) == "tier2"


def test_cheapest_tier_fixed_by_rerank_only():
    record = _record("q-3", {"baseline": False, "hybrid-v1": False, "rerank-v1": True})
    assert cheapest_tier(record) == "tier2"


def test_cheapest_tier_fixed_only_by_agentic():
    record = _record("q-4", {"baseline": False, "hybrid-v1": False, "rerank-v1": False, "agentic-v1": True})
    assert cheapest_tier(record) == "tier3"


def test_cheapest_tier_unfixed_by_anything():
    record = _record("q-5", {"baseline": False, "hybrid-v1": False, "rerank-v1": False, "agentic-v1": False})
    assert cheapest_tier(record) == "unfixed"


def test_compute_oracle_recall_and_cost_accounting():
    records = [
        _record("q-1", {"baseline": True}),  # tier1, cost=1
        _record("q-2", {"baseline": True}),  # tier1, cost=1
        _record("q-3", {"baseline": False, "hybrid-v1": True}),  # tier2, cost=1+10
        _record("q-4", {"baseline": False, "agentic-v1": True}),  # tier3, cost=1+10+100
        _record("q-5", {"baseline": False}),  # unfixed, cost=1 (no wasted escalation)
    ]
    costs = TierCosts(tier1=1.0, tier2=10.0, tier3=100.0)

    result = compute_oracle(records, costs)

    assert result.total_scored == 5
    assert result.baseline_hits == 2
    assert result.fixed_by_tier2 == 1
    assert result.fixed_by_tier3 == 1
    assert result.unfixed == 1
    assert result.oracle_recall == 4 / 5
    assert result.oracle_cost == (1 + 1) + (1 + 10) + (1 + 10 + 100) + 1
    assert result.baseline_cost == 1.0 * 5
    assert result.always_agentic_cost == 100.0 * 5


def test_project_router_unescalated_entries_pay_only_tier1():
    records = [_record("q-1", {"baseline": True}, spread=0.9)]
    costs = TierCosts(tier1=1.0, tier2=10.0, tier3=100.0)

    result = project_router(records, threshold=0.05, costs=costs)

    assert result.escalated == 0
    assert result.escalation_rate == 0.0
    assert result.projected_recall == 1.0
    assert result.projected_cost == 1.0


def test_project_router_unescalated_miss_is_not_projected_as_fixed():
    # spread above threshold means the router never looks twice, even though
    # this entry is (unknown to the router) a genuine baseline miss.
    records = [_record("q-1", {"baseline": False}, spread=0.9)]
    costs = TierCosts(tier1=1.0, tier2=10.0, tier3=100.0)

    result = project_router(records, threshold=0.05, costs=costs)

    assert result.escalated == 0
    assert result.projected_recall == 0.0
    assert result.projected_cost == 1.0


def test_project_router_escalated_fixed_by_tier2_pays_tier1_plus_tier2_only():
    records = [_record("q-1", {"baseline": False, "hybrid-v1": True}, spread=0.01)]
    costs = TierCosts(tier1=1.0, tier2=10.0, tier3=100.0)

    result = project_router(records, threshold=0.05, costs=costs)

    assert result.escalated == 1
    assert result.projected_recall == 1.0
    assert result.projected_cost == 1.0 + 10.0


def test_project_router_unfixed_entry_still_pays_full_ladder_no_foresight():
    # Unlike compute_oracle, a real router can't know q-018-style entries are
    # unfixable in advance -- it pays for tier 3 anyway and still misses.
    records = [_record("q-1", {"baseline": False, "hybrid-v1": False, "rerank-v1": False, "agentic-v1": False}, spread=0.01)]
    costs = TierCosts(tier1=1.0, tier2=10.0, tier3=100.0)

    result = project_router(records, threshold=0.05, costs=costs)

    assert result.escalated == 1
    assert result.projected_recall == 0.0
    assert result.projected_cost == 1.0 + 10.0 + 100.0


def test_project_router_no_filter_pays_tier3_even_when_tier2_already_resolved():
    # tier2_filter=False: no cheap signal exists to skip tier 3, so even an
    # entry tier 2 already fixed pays the full ladder -- recall is unchanged
    # (additive escalation can't lose a chunk already held), only cost rises.
    records = [_record("q-1", {"baseline": False, "hybrid-v1": True}, spread=0.01)]
    costs = TierCosts(tier1=1.0, tier2=10.0, tier3=100.0)

    with_filter = project_router(records, threshold=0.05, costs=costs, tier2_filter=True)
    no_filter = project_router(records, threshold=0.05, costs=costs, tier2_filter=False)

    assert with_filter.projected_cost == 1.0 + 10.0
    assert no_filter.projected_cost == 1.0 + 10.0 + 100.0
    assert with_filter.projected_recall == no_filter.projected_recall == 1.0


def test_project_router_no_filter_unfixed_entry_same_as_with_filter():
    # An unfixed entry pays the full ladder either way -- there was never a
    # tier2 resolution to skip past.
    records = [_record("q-1", {"baseline": False, "hybrid-v1": False, "rerank-v1": False, "agentic-v1": False}, spread=0.01)]
    costs = TierCosts(tier1=1.0, tier2=10.0, tier3=100.0)

    with_filter = project_router(records, threshold=0.05, costs=costs, tier2_filter=True)
    no_filter = project_router(records, threshold=0.05, costs=costs, tier2_filter=False)

    assert with_filter.projected_cost == no_filter.projected_cost == 1.0 + 10.0 + 100.0
    assert with_filter.projected_recall == no_filter.projected_recall == 0.0


def test_project_router_escalation_rate_and_recall_across_mixed_population():
    records = [
        _record("q-1", {"baseline": True}, spread=0.9),  # not escalated, hit
        _record("q-2", {"baseline": False, "hybrid-v1": True}, spread=0.01),  # escalated, tier2 fixes
        _record("q-3", {"baseline": False, "agentic-v1": True}, spread=0.01),  # escalated, tier3 fixes
    ]
    costs = TierCosts(tier1=1.0, tier2=10.0, tier3=100.0)

    result = project_router(records, threshold=0.05, costs=costs)

    assert result.escalated == 2
    assert result.escalation_rate == 2 / 3
    assert result.projected_recall == 3 / 3
    assert result.projected_cost == 1.0 + (1.0 + 10.0) + (1.0 + 10.0 + 100.0)
