# Router cost projection (Phase 5, T4.1)

`fb_rules`, 53 baseline-scored entries (13 misses, 40 hits). Escalation rule: escalate to tier 2 when `spread <= threshold`. Two cost columns, because T4.1b (below) found no cheap signal to decide tier2->tier3: **with-filter** assumes a tier2->tier3 stopping signal exists (an upper bound, not yet buildable); **no-filter** is the realistic number -- every tier-2-reached entry proceeds to tier 3 unconditionally. Recall is identical in both columns (additive escalation means an unneeded tier 3 pass can't lose a chunk already held).

Of the 13 misses (constant across every threshold below, since all three catch every miss): 8 resolved at tier 2, 4 need tier 3, 1 unfixed by anything Phase 4 ever ran (still pays the full ladder and still misses, under either column).

Reference points: baseline alone costs 170,513 for 75.5% recall; always-agentic costs 618,459 for 98.1% recall; the oracle (perfect foresight, stops early on `q-018`) costs 255,427 for the same 98.1% (`evals/analysis/oracle.md`).

The fitted threshold (0.051049) is computed precisely here as max(miss spread) + 0.0002 -- `evals/analysis/separation.md`'s own sweep table displays its closest row as "0.051" too, but that row's exact value (0.05090749..., one hit's own spread, picked up by chance from an evenly-spaced sparse sample of observed scores) is a different number that happens to round the same way. Both separate the same 13 misses from the same 40 hits except for one boundary entry (`q-013`); the difference is immaterial to the verdict but stated here rather than silently reconciled.

| threshold | escalation rate | misses caught | hits wrongly escalated | projected recall | cost (with-filter) | cost (no-filter) | saving vs agentic (no-filter) |
|---|---|---|---|---|---|---|---|
| 0.0510 (fitted) | 45.3% | 13/13 | 11/40 | 98.1% | 305,334 | 527,046 | 14.8% |
| 0.0610 (+0.010 margin) | 52.8% | 13/13 | 15/40 | 98.1% | 318,080 | 586,468 | 5.2% |
| 0.0710 (+0.020 margin) | 56.6% | 13/13 | 17/40 | 98.1% | 324,453 | 616,179 | 0.4% |

**Realistic number (no tier2->tier3 filter, per T4.1b): at the fitted threshold, projected cost is 527,046** against always-agentic's 618,459 -- a projected saving of 14.8%, for the identical 98.1% recall ceiling (the router cannot beat agentic's recall, only its cost, per plan.md's Milestone 4 framing). This is the number T4.2's go/no-go decision uses.
