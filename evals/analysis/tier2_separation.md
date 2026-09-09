# Tier 2 -> tier 3 signal characterization (Phase 5, T4.1b)

The 24 entries `fb_rules` escalates at the tier1 threshold (spread <= 0.051049), re-retrieved with tier 2's own combined hybrid+rerank config (mode=hybrid, candidate_k=20, rrf_k=60, reranker=Xenova/ms-marco-MiniLM-L-6-v2) -- a real retrieval, not a reuse of tier 1's scores, since this scale is the cross-encoder's, not cosine similarity. Label: resolved after tier 1 + tier 2 additively (baseline hit, or hybrid-v1/rerank-v1 hit) -- 19 resolved, 5 still need tier 3 or are unfixed by anything Phase 4 ran. All four scale-independent candidate signals tested, not just `spread` -- `count_above` is excluded, its absolute threshold has no meaning on the reranker's score scale.

| signal | AUC | 95% CI | clears bar? |
|---|---|---|---|
| `top1` | 0.611 | [0.284, 0.895] | no |
| `margin` | 0.432 | [0.099, 0.775] | no |
| `spread` | 0.611 | [0.333, 0.870] | no |
| `doc_agreement` | 0.221 | [0.056, 0.405] | no |

Chance bar: AUC >= 0.65 and CI excludes 0.5. n=24 (5 negative).

**Verdict: none of the four candidate signals clears the bar on this population.** Tier 3 must be entered unconditionally for every tier-2-reached entry that reaches this point -- there is no cheap way, with any of these signals at this sample size, to tell a tier-2-resolved entry from one that still needs tier 3. This raises the router's realistic projected cost well above what an oracle-informed stop-at-tier-2 would suggest -- see `router_projection.md`'s revised, no-filter cost line.
