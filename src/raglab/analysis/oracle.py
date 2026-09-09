"""Per-tier perfect-routing ceiling (Phase 5, T2.4).

For each of the baseline's recall misses, the cheapest Phase 4 tier that
already fixed it -- computed entirely from recorded Phase 4 outcomes, since
hybrid-v1, rerank-v1, and agentic-v1 already ran their own recall_hit for
every fb_rules entry. A perfect router has foresight: it never pays for a
tier that (per Phase 4's own record) wouldn't have helped.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .signal_study import SignalRecord

TIER_1 = "baseline"
# Tier 2 is "hybrid + rerank" as one rung (plan.md Architecture), but Phase 4
# only ever ran them standalone -- an entry counts as tier-2-fixable if
# either one independently found it, which is an upper bound on what a real
# combined tier 2 would do, not a measurement of one.
TIER_2_CANDIDATES = ("hybrid-v1", "rerank-v1")
TIER_3 = "agentic-v1"

CheapestTier = Literal["tier1", "tier2", "tier3", "unfixed"]


def cheapest_tier(record: SignalRecord) -> CheapestTier:
    """'tier1' if baseline already hit (nothing to route). 'tier2' if either
    tier-2 candidate found it. 'tier3' if only agentic did. 'unfixed' if
    nothing in Phase 4 ever got this entry right."""
    if record.recall_hit.get(TIER_1):
        return "tier1"
    if any(record.recall_hit.get(name) for name in TIER_2_CANDIDATES):
        return "tier2"
    if record.recall_hit.get(TIER_3):
        return "tier3"
    return "unfixed"


@dataclass(frozen=True)
class TierCosts:
    """Mean input tokens per entry for each tier, from Phase 4's own
    reports -- tier2's cost is the average of hybrid-v1 and rerank-v1's
    measured means, since no combined config has been run yet."""

    tier1: float
    tier2: float
    tier3: float


@dataclass(frozen=True)
class OracleResult:
    total_scored: int
    baseline_hits: int
    fixed_by_tier2: int
    fixed_by_tier3: int
    unfixed: int
    oracle_recall: float
    oracle_cost: float
    baseline_cost: float
    always_agentic_cost: float


@dataclass(frozen=True)
class RouterProjection:
    threshold: float
    total: int
    escalated: int
    escalation_rate: float
    projected_recall: float
    projected_cost: float


def project_router(
    records: list[SignalRecord], threshold: float, costs: TierCosts, *, tier2_filter: bool = True
) -> RouterProjection:
    """Cost/recall projection for one tier1->tier2 escalation threshold on
    `spread` (escalate when spread <= threshold).

    `tier2_filter=True` assumes a tier2->tier3 stopping signal exists --
    skip tier 3 once tier 1 or tier 2 already resolved the entry. This is an
    upper bound on what the ladder could achieve, not what's buildable
    today: T4.1b found no signal clears the chance bar for that decision.
    `tier2_filter=False` is the realistic number -- every tier-2-reached
    entry proceeds to tier 3 unconditionally, since there's no cheap way to
    tell a resolved entry from one that still needs it. Recall is identical
    either way (additive escalation means an unnecessary tier 3 pass can't
    lose a chunk already held); only cost differs.

    Differs from `compute_oracle` even with `tier2_filter=True`: an entry
    Phase 4 shows nothing ever fixes (`q-018`) still pays for tier 3 here,
    since a real router has no foreknowledge that escalating won't help,
    unlike the oracle's perfect-foresight assumption. `records` must already
    be filtered to one gold set's baseline-scored entries.
    """
    escalated = 0
    hits = 0
    cost = 0.0

    for record in records:
        if record.signals.spread > threshold:
            cost += costs.tier1
            if record.recall_hit.get("baseline"):
                hits += 1
            continue

        escalated += 1
        cost += costs.tier1 + costs.tier2
        tier = cheapest_tier(record)
        resolved_by_tier2 = tier in ("tier1", "tier2")
        if resolved_by_tier2 and tier2_filter:
            hits += 1
            continue

        cost += costs.tier3
        if resolved_by_tier2 or tier == "tier3":
            hits += 1
        # tier == "unfixed": still pays tier 3's cost, still a miss --
        # a real router can't know in advance that escalating won't help.

    total = len(records)
    return RouterProjection(
        threshold=threshold,
        total=total,
        escalated=escalated,
        escalation_rate=escalated / total if total else 0.0,
        projected_recall=hits / total if total else 0.0,
        projected_cost=cost,
    )


def compute_oracle(records: list[SignalRecord], costs: TierCosts) -> OracleResult:
    """`records` must already be filtered to one gold set's baseline-scored
    entries (signal_study.baseline_scored_records) -- recall_hit is only
    meaningful within a single gold set's own baseline run."""
    baseline_hits = 0
    fixed_by_tier2 = 0
    fixed_by_tier3 = 0
    unfixed = 0
    oracle_cost = 0.0

    for record in records:
        tier = cheapest_tier(record)
        if tier == "tier1":
            baseline_hits += 1
            oracle_cost += costs.tier1
        elif tier == "tier2":
            fixed_by_tier2 += 1
            oracle_cost += costs.tier1 + costs.tier2
        elif tier == "tier3":
            fixed_by_tier3 += 1
            oracle_cost += costs.tier1 + costs.tier2 + costs.tier3
        else:
            # A perfect router has foresight: escalating further wouldn't
            # have helped either, per Phase 4's own record, so it doesn't pay for it.
            unfixed += 1
            oracle_cost += costs.tier1

    total = len(records)
    oracle_recall = (baseline_hits + fixed_by_tier2 + fixed_by_tier3) / total if total else 0.0

    return OracleResult(
        total_scored=total,
        baseline_hits=baseline_hits,
        fixed_by_tier2=fixed_by_tier2,
        fixed_by_tier3=fixed_by_tier3,
        unfixed=unfixed,
        oracle_recall=oracle_recall,
        oracle_cost=oracle_cost,
        baseline_cost=costs.tier1 * total,
        always_agentic_cost=costs.tier3 * total,
    )
