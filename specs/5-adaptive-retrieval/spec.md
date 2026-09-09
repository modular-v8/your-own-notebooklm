# spec: Phase 5 — Adaptive Retrieval & Citation Discipline

## outcome

Phase 4 established that agentic retrieval reaches 98.1% recall against the baseline's 75.5%, with zero cost to recall or coverage anywhere, and pays for it in two currencies: 3.6× the tokens, and twelve citation-precision regressions caused by carrying a wider chunk union than it needs. This phase tries to stop paying both.

It opens with two experiments that cost nothing. The first splits the token accounting to find out whether agentic's 3.6× is real or partly an artifact of counting cache reads at face value. The second asks, entirely offline against artifacts that already exist, whether any signal available at retrieval time predicts when the baseline is about to fail — because if one does, most questions never need to escalate at all.

Only then does anything get built or spent.

## in scope

- **Usage instrumentation**: split `input_tokens` into fresh, cache-creation, and cache-read in the report. Zero model calls, and it may revise Phase 4's cost verdict.
- **Offline router simulation** against existing Phase 4 artifacts: does a retrieval-time signal — top-1 score, score margin, count above threshold, or similar — separate the baseline's 14 recall misses from its 43 hits? Zero model calls.
- **Oracle upper bound**, computed offline: the recall and cost a perfect router would achieve, as the ceiling every real router is measured against.
- An `AdaptivePipeline` with a three-tier ladder: dense single-shot, then hybrid + reranking, then agentic, escalating on the measured signal.
- **Model self-assessment** as an escalation signal if no cheap proxy separates the two groups — its own experiment, with its own cost measured.
- **Context pruning** inside the agentic loop: keep the top-N chunks by score across all calls rather than their union.
- **Citation discipline** as a prompt change, tested only if pruning does not fix citation precision on its own.
- A revised adoption rule with per-metric granularity.

## out of scope

- **Web UI, FastAPI, React.** Deferred a fifth time - for a good reason.
- **New retrieval techniques.** The ladder's rungs are Phase 4's already-measured configurations, reused. Nothing new is invented here.
- **Re-running Phase 4's rejected techniques as standalone candidates.** They were measured; those results stand.
- **New corpora or new gold entries.** The gold set is frozen at 99 entries, so Phase 5's numbers compare directly against Phase 4's.
- **Changing the judge, the embedding model, the any-overlap rule, chunking defaults, or the citation mechanism.**
- **Production concerns** — latency, concurrency, deployment.

## users & context

Unchanged: one developer, Windows 10, terminal, no GPU, a Claude subscription whose five-hour window is the binding resource.

The working loop differs from Phase 4 in one important way: **the first two milestones are pure analysis over artifacts that already exist.** Phase 4 could not answer a question without spending tokens. This phase can, at least at the start, and the sequencing exploits that deliberately — the cheapest experiments are also the ones most likely to invalidate the phase's premise, so they go first.

## constraints

- Everything from Phases 0–4 carries forward: Python 3.12 via `uv`, no PyTorch, no Docker, local-first, clone-and-run, minimal dependencies, `agent_sdk` as the working provider.
- **The frozen Phase 4 baseline remains the paired reference.** Phase 5's comparisons run against the same artifact Phase 4 used, so results from both phases sit on one scale.
- The judge, embedding model, any-overlap rule, chunking defaults, and citation mechanism are unchanged.
- **The ladder's rungs reuse Phase 4's exact configurations** — `hybrid-v1`, `rerank-v1`, `agentic-v1` — so each rung's standalone behavior is already characterized and any difference is attributable to the routing, not to a retuned rung.
- The gold set is frozen at 99 entries.

## data & integrations

**No new external service.** Everything runs through the existing provider and the existing local index.

**Usage split** — `UsageReport` gains `fresh_input_tokens`, `cache_creation_tokens`, and `cache_read_tokens` alongside the existing summed `input_tokens`, which keeps its current meaning so prior reports stay comparable.

**Router decision, recorded per entry** — the tier reached, the signal's value at each escalation point, and the token cost attributed to each tier. Without this a router's behavior is uninspectable, and the phase's central question is *why* it escalated, not just how often.

**Offline simulation artifacts** — a table over Phase 4's existing per-entry data: for each candidate signal, how cleanly it separates the baseline's misses from its hits, and what a router using it would have scored and cost. Written to `evals/analysis/`, since it is derived rather than a run.

**Prior reports remain readable.** All new fields are optional with defaults, following the pattern established in Phases 2, 3, and 4.

## prior decisions

- **The adoption rule gains per-metric granularity.** Zero regressions on `recall_hit` and `coverage`; a bounded `citation_precision` regression is tolerated when it is the only cost. Phase 4's flat rule rejected a technique that dominated every primary metric and lost nothing but citation hygiene, and its own as-built notes named that as the case for revisiting granularity. This is not a relaxation of standards — it is the distinction between losing the answer and citing it loosely, made explicit.
- **Escalation is a ladder, not a switch.** Hybrid and reranking both improved recall in Phase 4 and were rejected only for crowding a needed chunk out of a fixed top-k. Crowding costs far less when a tier is reached only by questions the cheaper tier already failed, so both become useful as rungs even though neither survived as a replacement.
- **A model self-assessment call is the fallback escalation signal.** At roughly 1K tokens against agentic's 16.5K it pays for itself at even moderate accuracy, and it is measurable as its own experiment rather than an assumption.
- **Pruning is tested before any prompt change.** Citation dilution was traced directly to the accumulated chunk union, so pruning may fix it outright. Bundling the two would reproduce exactly the attribution failure Phase 4's design existed to prevent.
- **The cheapest experiments run first, deliberately including the one that could undercut the phase.** If the usage split shows agentic's real incremental cost is far below 3.6×, the case for routing weakens considerably — and that is worth knowing before building a router, not after.

## requirements

### always active

- The system SHALL report fresh, cache-creation, and cache-read input tokens separately, while leaving the existing summed `input_tokens` unchanged.
- The system SHALL record, per entry, the tier reached, the escalation signal's value, and the token cost attributed to each tier.
- The system SHALL allow each ladder tier to be enabled or disabled independently, so the ladder collapses to any prefix of itself.
- The system SHALL reuse Phase 4's frozen baseline as the paired comparison reference.
- The system SHALL treat `recall_hit` and `coverage` as strict-no-regression metrics, and `citation_precision` as bounded.
- The system SHALL leave the judge, embedding model, any-overlap rule, and gold set unchanged.

### event-driven

- WHEN the offline simulation runs, the system SHALL report, for each candidate signal, its separation between the baseline's recall misses and hits, and the recall and cost a router using it would have achieved.
- WHEN the oracle upper bound is computed, the system SHALL report the recall and cost of perfect routing as the ceiling for every real router.
- WHEN an entry is escalated, the system SHALL record which signal fired and at what value.
- WHEN the agentic tier runs under pruning, the system SHALL retain the top-N chunks by score across all calls and record how many were discarded.
- WHEN an experiment is compared against the baseline, the system SHALL apply the per-metric adoption rule and state which metric each regression fell on.

### unwanted behavior

- IF no candidate signal separates the baseline's misses from its hits better than chance, the system SHALL report that finding and SHALL NOT proceed to build a proxy-based router.
- IF the self-assessment signal is also no better than chance, the system SHALL report routing as unviable on this corpus and stop, rather than escalating everything.
- IF pruning causes any `recall_hit` or `coverage` regression, the pruning configuration SHALL be rejected outright, regardless of its citation-precision gain.
- IF a router escalates every entry, the system SHALL report it as degenerate and equivalent to running the top tier alone.
- IF the usage split shows agentic's incremental cost is under 2× the baseline, the system SHALL state that the phase's cost premise is weakened before any router is built.

## risks & open questions

- **No signal may separate the two groups.** The baseline's 14 misses might look identical at retrieval time to its 43 hits, in which case cheap routing is impossible on this corpus. That is a legitimate finding and it ends the phase early, at almost no cost — which is precisely why it is measured first.
- **Self-assessment may be systematically overconfident.** A model judging whether its own retrieved context suffices is being asked to know what it does not know. It may escalate too rarely, or too often, and either failure makes it useless as a router.
- **Tier 2 may not help escalated questions.** Hybrid and reranking crowd chunks out of a fixed window; the questions that reach tier 2 are exactly the hard multi-source ones where crowding hurt most in Phase 4.
- **Pruning may drop a needed chunk.** Keeping top-N by score is a heuristic, and the score that ranked a chunk low is the same score that missed it in the first place. The strict-on-recall rule is what catches this.
- **The first task may weaken the phase's own premise.** If the usage split shows most of agentic's cost is cached reads, routing buys less than it appears to. Stated here so it reads as a designed outcome rather than a surprise.

## acceptance criteria

- [x] Run reports carry fresh, cache-creation, and cache-read input tokens separately, and Phase 4's agentic cost is restated under that split.
- [x] The offline simulation reports, for every candidate signal, its separation between the baseline's misses and hits — with no model calls made. (The frozen artifact has 13 misses/40 hits, not the 14/43 named above — a one-off miscount in this document, corrected in plan.md's As-built notes; same underlying run, same 75.5% recall@k.)
- [x] The oracle upper bound is stated as a recall figure and a token cost, and every router is reported against it.
- [ ] **Blocked**: A router built on the best available signal is run on `fb_rules` and compared against the frozen Phase 4 baseline. T4.2's cost gate found the router's real-cost-adjusted saving negative (−3.4%) before any pipeline code was written — no router was built, so none could be run. See plan.md As-built notes (T4.1/T4.1b/T4.2) for the full arithmetic.
- [ ] **Blocked, same reason**: escalation rate, tier distribution, and per-tier token cost reported for every router run. T4.1's *projected* figures exist (`evals/analysis/router_projection.md`); there is no live run to report actuals for.
- [x] N/A — a signal (`spread`) cleared the chance bar in M2, so the "no signal beats chance" fallback path was never entered.
- [x] Context pruning is implemented and proven — before any live run, and before any citation prompt change was written — structurally incapable of moving `citation_precision` (the metric depends only on `cited` against corpus-wide `chunk_spans`, never on `retrieved`'s membership). No live pruning run was needed to establish this, which is why none preceded the prompt change.
- [x] N/A — pruning was never live-run (see above), so no `recall_hit`/`coverage` regression occurred to reject.
- [x] The adopted configuration's recall, coverage, citation precision, and token cost are stated against both the Phase 4 baseline and `agentic-v1`. The adopted configuration *is* `agentic-v1`, unchanged — every mitigation this phase tried (router, pruning, citation prompt) was rejected or not adopted, so the comparison is Phase 4's own frozen numbers, restated in plan.md's As-built notes.
- [x] `uv run pytest -q` green; `uv pip list` contains no `torch`.
