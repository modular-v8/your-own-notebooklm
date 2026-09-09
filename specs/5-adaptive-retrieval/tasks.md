# Tasks: Phase 5 — Adaptive Retrieval & Citation Discipline

Milestones 1–3 are drafted here. Milestones 4–7 depend on which signal survives
the gate in M3 — the router's shape, its threshold, and whether a
self-assessment call is in the loop are all outputs of that gate, so drafting
them now would mean drafting them twice.

**Standing rule, unchanged since Phase 4:** no task performs a live provider run
without explicit confirmation first, naming the provider and expected token cost.

**Cost through M3: at most ~57K input tokens**, and only if the gate falls
through to the self-assessment probe. M1 and M2 spend nothing.

---

## Milestone 1: Usage Split and Score Recording

Zero model calls. This milestone can weaken the phase's own premise, which is
why it runs first.

- [x] **T1.1** Change `Usage` in `providers/base.py` to carry `fresh_input_tokens`, `cache_creation_tokens`, and `cache_read_tokens` alongside `input_tokens`, with `input_tokens` keeping its current summed meaning.
  - Acceptance: existing call sites reading `usage.input_tokens` are unchanged in behavior; `uv run pytest -q` green.
  - Refs: spec §data & integrations (usage split), plan §Data Model
  - Depends on: none

- [x] **T1.2** Populate the three fields in `providers/agent_sdk.py`, replacing the current sum at `agent_sdk.py:66-70` with a split that also still sums.
  - Acceptance: a unit test with a scripted `ResultMessage` asserts all four values; the summed field equals the sum of the other three.
  - Refs: plan §File/Module Structure
  - Depends on: T1.1

- [x] **T1.3** Populate the same fields for `AnthropicProvider` and `OpenRouterProvider`, using zeros where the provider reports no cache breakdown.
  - Acceptance: no provider raises on a response lacking cache fields; zeros are recorded, not `None`.
  - Refs: spec §requirements
  - Depends on: T1.1

- [x] **T1.4** Add `fresh`, `cache_creation`, `cache_read` to `UsageReport` and `retrieved_scores` to `EntryReport`, all optional with defaults; wire scores through from the retriever.
  - Acceptance: a Phase 4 report still loads unchanged; a new run records per-chunk scores in entry order.
  - Refs: spec §data & integrations, plan §Data Model
  - Depends on: T1.1

- [x] **T1.5** Restate Phase 4's `agentic-v1` cost under the split, using the existing 665K run's raw provider data if recoverable, or a single cheap re-run of a handful of entries if not. **Confirm before any re-run.**
  - Acceptance: a written statement of what share of agentic's 665K was cache reads, and the resulting real incremental multiple against the baseline's 183K.
  - Refs: spec §outcome, plan §Sequencing M1
  - Depends on: T1.2, T1.4
  - Done: raw split unrecoverable from the existing report; confirmed and ran a 3-entry probe instead. 48.9% of the probe's tokens were cache reads; see plan.md As-built notes.

- [x] **T1.6** **Premise check.** If T1.5 shows agentic's real incremental cost is under 2×, write that finding prominently in `plan.md`'s as-built notes and flag that the routing premise is weakened before milestone 4 is started.
  - Acceptance: an explicit statement either way — "premise holds at Nx" or "premise weakened, agentic costs only Nx" — not silence.
  - Refs: spec §unwanted behavior (premise weakened), plan §Open Risks
  - Depends on: T1.5
  - Done: premise holds at ~2.49× real cost (down from the naive 3.63× raw-token count) — above the 2× floor. See plan.md As-built notes.

---

## Milestone 2: Offline Signal Study and Oracle

Zero model calls. Everything here reads artifacts already on disk and drives the
local index.

- [x] **T2.1** Implement `retrieval/signals.py` computing `top1`, `margin`, `spread`, `count_above(θ)`, and `doc_agreement` from a single dense retrieval.
  - Acceptance: `tests/test_signals.py` verifies each on a hand-built retrieval with known scores, including the degenerate single-chunk case.
  - Refs: plan §Data Model (candidate signals)
  - Depends on: none

- [x] **T2.2** Build `analysis/signal_study.py`: for all 99 gold entries, recompute signals locally from the on-disk index and join each entry's `recall_hit` from the Phase 4 baseline, hybrid, rerank, and agentic reports into `evals/analysis/signals.json`.
  - Acceptance: the file covers every entry; no provider is constructed anywhere in the path; runtime is seconds, not minutes.
  - Refs: plan §Approach Summary (retrieval is deterministic and local)
  - Depends on: T2.1

- [x] **T2.3** Compute AUC with a bootstrap confidence interval for each signal against the baseline's recall misses, plus the full threshold sweep — at each threshold, escalation rate, misses caught, and hits wrongly escalated.
  - Acceptance: `tests/test_signal_study.py` covers a perfectly separable case (AUC 1.0), a random case (CI containing 0.50), and an inverted signal (AUC below 0.50).
  - Refs: plan §Tech Stack (separation measure)
  - Depends on: T2.2

- [x] **T2.4** Implement `analysis/oracle.py`: for each of the baseline's 14 misses, find the cheapest Phase 4 tier that fixed it, and compute perfect-routing recall and token cost for the ladder.
  - Acceptance: `evals/analysis/oracle.md` states oracle recall, oracle cost, and — for comparison — the cost of always-agentic and of the baseline alone.
  - Refs: spec §in scope (oracle upper bound), plan §Tech Stack
  - Depends on: T2.2

- [x] **T2.5** Write `evals/analysis/separation.md`: per-signal AUC and CI, the threshold sweep, the oracle ceiling, and a plain verdict on whether any signal clears AUC ≥ 0.65 with its CI excluding 0.50.
  - Acceptance: the verdict is stated as a single unambiguous sentence naming the winning signal and threshold, or naming none.
  - Refs: spec §acceptance criteria, plan §Sequencing M2
  - Depends on: T2.3, T2.4
  - Done: `spread` clears the bar (AUC=0.821, CI=[0.700,0.922]); see plan.md As-built notes.

---

## Milestone 3: The Gate

The only milestone that may end the phase.

- [x] **T3.1** Apply the gate to T2.5's verdict. A signal clears → record it as the router's signal and threshold, and milestones 4–7 get drafted. Nothing clears → proceed to T3.2.
  - Acceptance: a written decision naming the signal and threshold, or stating that none cleared and why the fallback is being run.
  - Refs: spec §unwanted behavior (no signal beats chance), plan §Sequencing M3
  - Depends on: T2.5
  - Done: `spread` clears the bar (AUC=0.821, CI=[0.700,0.922]). Router signal = `spread`, tier1→tier2 threshold = 0.051 (the smallest sweep point that catches all 13/13 known misses: 43.4% escalation rate, 10/40 hits wrongly escalated). See plan.md As-built notes.

- [x] **T3.2** *(only if nothing cleared)* Implement the self-assessment probe: after tier-1 retrieval, one short call asking whether the retrieved context suffices to answer, returning a yes/no plus confidence.
  - Not run: `spread` cleared offline in M2, so the fallback is unneeded per this task's own condition.

- [x] **T3.3** *(only if nothing cleared)* Run the probe over all 57 `fb_rules` entries and score it against known baseline outcomes by the same AUC-and-CI bar. **Confirm cost first (~57K input tokens, `agent_sdk`).**
  - Not run: same reason as T3.2. The ~57K token budget for this probe is unspent.

- [x] **T3.4** Record the phase's routing verdict. A signal cleared, offline or via self-assessment → milestones 4–7 are drafted against it. Neither cleared → **stop, and write routing up as unviable on this corpus**, with the separation numbers as the evidence.
  - Acceptance: an as-built section stating the verdict, the numbers behind it, and — if stopping — what a larger or different corpus would need for routing to become viable.
  - Refs: spec §unwanted behavior, plan §Sequencing M3
  - Depends on: T3.1, T3.3
  - Done: routing is viable on this corpus via `spread`. Milestones 4–7 drafted below.

---

## Milestone 4: The Adaptive Router

The gate opened on `spread` (AUC 0.821, CI [0.700, 0.922]). Three findings from
a further free offline pass reshape this milestone before any tokens are spent:

- **Escalation fires on LOW spread** (`spread ≤ threshold`), not high. Wiring it
  the other way escalates exactly the entries that were already correct.
- **`q-056` regresses under both `hybrid-v1` and `rerank-v1` standalone**, and
  the threshold escalates it despite the baseline answering it correctly. A
  substitutive tier 2 breaks it and the strict-on-recall rule then rejects the
  whole router. Escalation must be **additive**.
- **The ladder's ceiling is 52/53 = 98.1%**, identical to `agentic-v1`:
  8 of 13 misses are fixable at tier 2, 4 need tier 3, and `q-018` is fixed by
  nothing. The router can only match agentic on recall — its entire value is cost.

- [x] **T4.1** Extend the offline study: for the fitted threshold and at least two margin-added thresholds, report escalation rate, misses caught, false escalations, and — using Phase 4's per-entry outcomes — the tier each escalation would need and the resulting projected cost.
  - Acceptance: a table in `evals/analysis/router_projection.md` giving projected recall and cost per threshold, against the oracle ceiling and against `agentic-v1`. **Zero model calls.**
  - Refs: plan §Tech Stack (threshold margin), spec §acceptance criteria
  - Depends on: T3.4
  - Done: fitted threshold computed precisely as 0.051049 (max miss spread + 0.0002; a rounding-coincidence discrepancy against `separation.md`'s own sweep-table value is reconciled in `router_projection.md`). At the fitted threshold: 45.3% escalation, 13/13 misses caught, 11/40 hits wrongly escalated. See plan.md As-built notes for the full table and the with-filter/no-filter cost split T4.1b's finding required.

- [x] **T4.1b** Characterise the **tier 2 → tier 3** decision, which the M2 study never touched: recompute `spread` after an additive hybrid+rerank retrieval for the escalated entries, and score it against whether tier 2 actually fixed them. The tier-1 threshold cannot be assumed to transfer.
  - Acceptance: an AUC with CI for the post-tier-2 signal against the same bar, or an explicit finding that it fails and tier 3 must be entered by a different rule. **Zero model calls** — hybrid and reranking are both local and deterministic.
  - Refs: plan §Tech Stack (separation measure), spec §risks
  - Depends on: T4.1
  - Done: tested all four scale-independent signals (`top1`, `margin`, `spread`, `doc_agreement`; `count_above`'s threshold has no meaning on the reranker's scale) on a real combined hybrid+rerank retrieval for the 24 escalated entries — none clears the bar (best: `top1`/`spread` at AUC=0.611). Tier 3 must fire unconditionally once tier 2 is reached. See `evals/analysis/tier2_separation.md`.

- [x] **T4.2** **Go/no-go on cost.** If the best threshold's projected cost saving over `agentic-v1` is under 25% once the 2.49× real-cost figure from T1.5 is applied, record that the router is not worth building and say so before T4.3.
  - Acceptance: an explicit statement — "projected saving N%, proceeding" or "projected saving N%, router not worth building" — with the arithmetic shown.
  - Refs: spec §unwanted behavior (degenerate router), plan §Open Risks
  - Depends on: T4.1
  - Done: **router not worth building.** Raw-token saving at the fitted threshold is 14.8% (527,046 vs 618,459) — already under 25%, and T4.1b's no-filter finding is what makes it that low (an oracle-informed stop-at-tier-2 would have projected 50.6%). Applying T1.5's 2.49× real-cost ratio (agentic's own tier-3 cost discounted to 68.7% of face value for its cache-read share; tier 1/2 are single-shot calls with no such discount) turns the saving **negative: -3.4%** — the router would cost more in real dollars than running `agentic-v1` on everything. T4.3–T4.6 are not implemented as a result. See plan.md As-built notes for the full arithmetic.

- [x] **T4.3** Implement `pipelines/adaptive.py`: tiers entered in order, each tier's candidates **added** to the accumulated set rather than replacing it, escalation on `spread ≤ threshold`, every entered tier charged.
  - Not run: T4.2 stopped the milestone here. Building the pipeline that T4.2 just showed isn't worth its cost would spend engineering effort on a config that fails its own gate before a token is spent.

- [x] **T4.4** Verify additivity offline against Phase 4 data: confirm that under an additive tier 2, none of the 11 false escalations — `q-056` in particular — can lose a chunk the baseline held.
  - Not run: same reason as T4.3. (The property itself was already confirmed for `q-056` specifically as part of T4.2's analysis, independent of whether the pipeline gets built.)

- [x] **T4.5** Add `adaptive-v1` to `experiments.toml` and run on `fb_rules`; compare against the frozen Phase 4 baseline and against `agentic-v1`. **Confirm cost first (~350K, `agent_sdk`).**
  - Not run: T4.2's negative verdict means there's no config to run. The ~350K token budget for this task is unspent.

- [x] **T4.6** Record the adoption decision under the per-metric rule — strict on `recall_hit` and `coverage`, bounded on `citation_precision`.
  - Done: adoption decision is "not built" — recorded in T4.2's Done note and plan.md's As-built notes, in place of a per-metric comparison there's no run to compare.

---

## Milestone 5: Context Pruning

Applies to both `agentic-v1` and the additive ladder, since both accumulate and
both therefore dilute citations the same way.

- [x] **T5.1** Add optional top-N pruning across accumulated chunks to `pipelines/agentic.py` and to `adaptive.py`, recording how many chunks were discarded per entry.
  - Acceptance: `tests/test_pruning.py` asserts top-N retention by score, the discarded count, and that pruning is a no-op when the accumulated set is already ≤ N.
  - Refs: spec §in scope (context pruning), plan §Tech Stack
  - Depends on: none
  - Done: implemented in `agentic.py` only (`adaptive.py` doesn't exist — M4's router wasn't built). **Important caveat found before any live call**: verified directly against `score_citations`'s actual formula that pruning `retrieved` cannot mechanically move `citation_precision` (it depends only on `cited` vs. corpus-wide `chunk_spans`) — it can only affect `recall_hit`/`coverage` (both genuinely depend on `retrieved`) and the `fabricated` list. See plan.md As-built notes for the full reasoning and what mechanism would actually be needed to move citation precision. T5.2+ need explicit confirmation before any live call and are not run.

- [x] **T5.2–T5.4** **Closed, not run — structural finding.** `score_citations` resolves precision against the corpus-wide `chunk_spans` map, explicitly *not* filtered by `retrieved` (`citations.py:74-79`, where the orthogonality of fabrication and precision is a deliberate documented choice). Post-hoc pruning of `retrieved` therefore cannot move `citation_precision` under any `N`. It can only move `fabricated` — turning legitimate citations into apparent fabrications — and `recall_hit`/`coverage`, which it can only degrade or leave flat. The runs would have cost ~250K–600K to confirm that a change with no upside is harmless. **~1.1M token budget unspent.**
  - The mechanism that *would* move citation precision is shrinking what the model reads before it answers. That is unreachable here: `AgentSDKProvider.complete()` runs the tool loop as one opaque internal cycle, so raglab controls what a tool call returns, never what the model has already read from earlier turns of the same conversation.

- [x] **T5.5** **No bound set — none is needed from this milestone.** Pruning cannot inform a citation-precision bound it cannot affect. The bound, if one is ever required, comes from M6's measured effect instead.

---

## Milestone 5b: Free Diagnosis Before Spending

Two zero-cost checks that decide whether M6 is worth running at all.

- [x] **T5b.1** Examine the 12 citation-precision regressions in Phase 4's `agentic-v1` report: for each, the chunks cited that miss every gold span, and whether they are plausibly load-bearing for the answer or merely adjacent context the model swept in.
  - Acceptance: a written characterisation. If the extra citations are chunks the answer genuinely rests on, no prompt instruction will remove them and M6 should not run. **Zero model calls.**
  - Refs: spec §in scope (citation discipline), plan §Sequencing
  - Depends on: T5.5
  - Done: read all 20 non-gold-overlapping citations across the 12 regressions against the model's own answer text (`any_overlap`-based classification verified to reproduce the report's recorded `citation_precision` exactly on 4 spot-checked entries). **15/20 (75%) are load-bearing** — content the answer text actually quotes or reasons from, just outside the narrow gold span; **5/20 (25%) are genuine adjacent noise** never referenced in the answer at all. Mixed result: M6 has a real but narrow target, not the bulk of the dilution. Full per-entry table in `evals/analysis/citation_dilution.md`.

- [x] **T5b.2** Check whether citation precision correlates with accumulated-set size across agentic's 57 entries. Dilution predicts a negative correlation; its absence would mean something other than set size is driving it.
  - Acceptance: a correlation coefficient and a plain reading of it. **Zero model calls.**
  - Refs: plan §Open Risks
  - Depends on: T5.1
  - Done: Pearson r = -0.380 (n=52, 5 not-in-document entries excluded — no gold spans to score precision against). Negative and non-trivial, consistent with the dilution hypothesis — though T5b.1 suggests it's partly "harder questions need fuller, more-cited answers" rather than purely carelessness. See `evals/analysis/citation_dilution.md`.

---

## Milestone 6: Citation Prompt

**Promoted: this is now the phase's only remaining live experiment.** M4's router
failed its cost gate and M5's pruning is structurally incapable, so a prompt
change is the sole surviving lever on the one metric blocking `agentic-v1`'s
adoption.

---

## Milestone 6: Citation Prompt

**Skipped entirely if T5.5 found pruning sufficient.**

- [x] **T6.1** Amend the answering prompt to instruct tight citation — cite only chunks a claim actually rests on — changing nothing else.
  - Acceptance: `git diff` touches only the citation instruction; `FakeProvider` tests still pass.
  - Refs: spec §in scope (citation discipline), plan §Sequencing M6
  - Depends on: T5.5
  - Done: `AgenticPipeline.SYSTEM_PROMPT` (`pipelines/agentic.py`) gained one sentence — "Cite tightly: name a chunk only if a specific claim in your answer depends on it, not every excerpt you searched or read along the way" — inserted between the citation-block instruction and the empty-citations fallback; nothing else in the prompt or pipeline changed. New test asserts the instruction is present. `uv run pytest -q`: 259 passed. Targets T5b.1's narrower finding (~25% of extra citations are genuinely unused, not the 75% that are load-bearing) rather than assuming the whole regression is fixable.

- [x] **T6.2** Run `agentic-v1` plus the tightened citation prompt on Phase 4's **20-entry hard subset**, not the full gold set. **Confirm cost first (~250K).**
  - Acceptance: citation precision against that subset's `agentic-v1` figures; recall and coverage confirmed unmoved, since a prompt change must not touch retrieval. If citation precision does not move on the subset, stop — do not pay for the full run.
  - Refs: plan §Integration Plan (subset before full), spec §acceptance criteria
  - Depends on: T6.1
  - Done: **citation precision did not improve — it dipped slightly, and stop condition triggered.** Same 20 entries, `agentic-v1`, 291,143 input tokens (confirmed and run). Aggregate: citation_precision 68.0%→65.6%, recall@k 100%→100% (unmoved), coverage 92.5%→92.5% (unmoved), 330,468→291,143 tokens (-11.9%). Per-entry (`compare_reports`, aligned for the two runs' different scratch-file paths but matching `entry_ids_fingerprint`): **4 wins, 4 losses, 12 ties — zero recall_hit/coverage changes anywhere, all churn on citation_precision.** Wins: `q-004` (0.67→1.0), `q-021` (0.5→0.8), `q-022` (0.5→0.67), `q-031` (0.25→0.33). Losses: `q-033` (1.0→0.25), `q-058` (1.0→0.67), `q-032` (0.5→0.33), `q-036` (0.25→0.14). Matches T5b.1's prediction of modest, not dramatic, movement — here manifesting as a wash rather than net improvement. See plan.md As-built notes.

- [x] **T6.3** Only if T6.2 moved citation precision materially: run full `fb_rules` and compare against the frozen Phase 4 baseline under the per-metric adoption rule. **Confirm cost first (~665K.)**
  - Not run: T6.2's own stopping condition triggered — citation precision did not move materially (net negative on aggregate, an even win/loss split per-entry). The ~665K token budget for the full run is unspent.

---

## Milestone 7: Final Configuration and Phase Report

- [x] **T7.1** Assemble the best surviving configuration — ladder plus pruning, plus the citation prompt if adopted — and run it on the full corpus. **Confirm cost first (~350K).**
  - Acceptance: one report covering all 99 entries under the final configuration.
  - Refs: spec §acceptance criteria
  - Depends on: T4.6, T5.5, T6.2
  - Done: **no new run needed — the best surviving configuration is Phase 4's own `agentic-v1`, unmodified.** Router (M4): not built. Pruning (M5): not live-run. Citation prompt (M6): not adopted, and made opt-in post-hoc so `agentic-v1`'s code stays byte-identical to Phase 4's frozen prompt (see plan.md As-built notes for that correction). The existing 665,135-token full `fb_rules` run already *is* this configuration's full-corpus result. **Scope note, not silently resolved**: `agentic-v1` has never been run against the other 4 gold sets (40 more entries, ~470K estimated) — out of scope for everything this phase measured (router/oracle/pruning/prompt were all `fb_rules`-only throughout) and not run without separate confirmation.

- [x] **T7.2** Write the phase's as-built notes in the format Phases 2–4 established.
  - Acceptance: results across every experiment; recall, coverage, citation precision, and cost stated against the Phase 4 baseline, against `agentic-v1`, and against the oracle ceiling; the escalation-rate and threshold-margin tradeoff stated plainly; every regression named.
  - Refs: spec §acceptance criteria
  - Depends on: T7.1
  - Done: full phase report in plan.md's As-built notes — comparison table, milestone-by-milestone summary (M1–M6), bottom-line verdict (`agentic-v1` rejected under Phase 4's rule, three independent mitigations tried and none adopted), and spec.md's acceptance criteria walked through one by one (checked, or blocked with reason). `spec.md` and this file both updated to reflect final status.

---

**Live cost if every milestone runs: ~2.3M input tokens.** Two gates can cut
that sharply — T4.2 can stop the router before it is built, and T5.5 can skip
milestone 6 entirely.

---

## Definition of Done

- [x] All tasks above checked off, and those in milestones 4–7 once drafted.
- [x] Every acceptance criterion in `spec.md` is met or explicitly recorded as blocked with its reason. (2 blocked: no router was built to run or report escalation stats for — see spec.md.)
- [x] `uv run pytest -q` green; `uv pip list` contains no `torch`. (262 passed.)
- [x] Phase 4's agentic cost is restated under the usage split. (≈2.49× real cost, T1.5/T1.6.)
- [x] The signal study's verdict is stated unambiguously, whichever way it fell. (`spread` clears the bar, AUC=0.821, CI=[0.700, 0.922], T2.5.)
- [ ] ~~If a router was built...~~ — N/A, no router was built.
- [x] If no router was built: the separation numbers are recorded as the finding, with what would have to change for routing to work. **What would have to change**: (1) a tier2→tier3 filter — none of four signals cleared the bar on this corpus (n=24, 5 negative); a larger corpus might reveal one at a workable sample size, or might not. (2) A cheaper tier 3, or a higher tier-2-alone fix rate, so fewer escalations need the full ladder — here only 8/13 misses resolve at tier 2, the other 5 need tier 3's full (discounted) cost regardless. (3) A sharper tier-1 signal (AUC well above 0.821) to cut the false-escalation rate below 11/40 without missing real misses. None of these are ruled out on a different corpus; none held here.
- [x] `plan.md` carries an as-built section in the format Phases 2–4 established.
