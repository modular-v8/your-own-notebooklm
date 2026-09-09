# Oracle upper bound (Phase 5, T2.4)

For each of the baseline's recall misses, the cheapest Phase 4 tier that already fixed it -- an upper bound, not a real router, computed entirely from recorded Phase 4 outcomes. Tier 2 (`hybrid-v1` + `rerank-v1`) counts an entry as fixed if either standalone config found it, since no combined tier-2 config has been run.

Per-entry mean input tokens, from Phase 4's own reports:
- tier 1 (baseline): 3,217
- tier 2 (avg of hybrid-v1 3,183 and rerank-v1 3,190): 3,186
- tier 3 (agentic-v1): 11,669

| | recall (53 entries) | cost |
|---|---|---|
| baseline alone | 40/53 = 75.5% | 170,513 |
| always-agentic | 52/53 = 98.1% | 618,459 |
| **oracle** | 52/53 = 98.1% | 255,427 |

Miss breakdown: 40 already hit by baseline, 8 fixed by tier 2, 4 fixed only by tier 3, 1 unfixed by anything Phase 4 ran.

Oracle recall (98.1%) against always-agentic's own measured recall on this subset (98.1%), at 41.3% of always-agentic's cost.
